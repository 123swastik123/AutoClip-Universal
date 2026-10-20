"""OpenAI-compatible client with multi-provider cascading fallback.

Supports free LLM API keys (Groq, Gemini, OpenRouter, Mistral, Together, etc.)
and custom base URLs with automatic fallback:
  1. Primary Model (Best model tried first)
  2. Fallback Model (Second best model used if primary fails/rate-limited)
  3. Local Fallback (Ollama gemma4:12b or custom local endpoint)

Used for judgment tasks: research, pattern extraction, candidate clip selection,
and edit directives. Every output is validated against a schema before ingestion.
"""
import json, os, time, urllib.request, urllib.error
from . import config  # Ensures .env is loaded on import

# Defaults
DEFAULT_LOCAL_BASE = "http://127.0.0.1:11434/v1"
DEFAULT_LOCAL_MODEL = "gemma4:12b"
DEFAULT_TIMEOUT = int(os.environ.get("AUTOCLIP_LLM_TIMEOUT", "60"))

_SCALARS = {"str": str, "float": (int, float), "int": int, "bool": bool}

def _check_type(val, typ, path, errors):
    if typ == "null":
        return True
    if typ.endswith("[]"):
        if not isinstance(val, list):
            errors.append(f"{path}: expected list of {typ[:-2]}")
            return False
        ok = True
        for i, x in enumerate(val):
            if not _check_type(x, typ[:-2], f"{path}[{i}]", errors):
                ok = False
        return ok
    if typ == "int":
        ok = (isinstance(val, int) and not isinstance(val, bool)) or (isinstance(val, float) and val.is_integer()) or (isinstance(val, str) and val.strip().lstrip('-').isdigit())
        if not ok:
            errors.append(f"{path}: expected int, got {type(val).__name__}")
        return ok
    if typ == "float":
        ok = isinstance(val, (int, float)) and not isinstance(val, bool)
        if not ok:
            errors.append(f"{path}: expected float, got {type(val).__name__}")
        return ok
    base = _SCALARS.get(typ)
    if base is None:
        return True
    ok = isinstance(val, base)
    if not ok:
        errors.append(f"{path}: expected {typ}, got {type(val).__name__}")
    return ok


def _validate_spec(spec, obj, path, errors):
    """Validate obj against spec. Spec: dict of key->rule.

    Rule forms:
      ("str", True)             scalar with required flag
      "str"                     scalar, optional
      "str[]"                   list of scalars
      {"$list": inner_spec}     list of objects matching inner_spec
      {key: inner_spec}         nested object (dict)
    """
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected object")
        return False
    for key, rule in spec.items():
        sub = f"{path}.{key}"
        if isinstance(rule, dict) and "$list" in rule:
            if key not in obj or obj[key] is None:
                errors.append(f"{sub}: missing required list")
                continue
            items = obj[key]
            if not isinstance(items, list):
                errors.append(f"{sub}: expected list")
                continue
            for i, it in enumerate(items):
                _validate_spec(rule["$list"], it, f"{sub}[{i}]", errors)
            continue
        if isinstance(rule, dict):
            if key not in obj or obj[key] is None:
                errors.append(f"{sub}: missing required")
                continue
            _validate_spec(rule, obj[key], sub, errors)
            continue
        req = False
        if isinstance(rule, tuple):
            req = rule[1] if len(rule) > 1 else False
            rule = rule[0]
        if key not in obj or obj[key] is None:
            if req and rule not in ("null",):
                errors.append(f"{sub}: missing required")
            continue
        if rule != "null" and rule != "any":
            if _check_type(obj[key], rule, sub, errors):
                if rule == "int" and not isinstance(obj[key], bool):
                    try:
                        obj[key] = int(round(float(obj[key])))
                    except Exception:
                        pass
                elif rule == "float" and not isinstance(obj[key], bool):
                    try:
                        obj[key] = float(obj[key])
                    except Exception:
                        pass
    return not errors


def _extract_json(content):
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    a, b = content.find("{"), content.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(content[a:b + 1])
        except json.JSONDecodeError:
            return None
    return None


def _is_local(url):
    return "127.0.0.1" in url or "localhost" in url


def get_providers():
    """Return configured LLM providers in priority order.

    Priority:
      1. Primary Provider (Best model - Groq, Gemini, OpenRouter, etc.)
      2. Fallback / Secondary Provider (Second best model)
      3. Cloud Provider (Free LLM Cloud Server for 24/7 access)
      4. Local Provider (Ollama or local offline LLM)
    """
    providers = []
    seen = set()

    # 1. Primary Provider (best model)
    pri_base = (os.environ.get("AUTOCLIP_PRIMARY_BASE_URL") or
                os.environ.get("OPENAI_BASE_URL") or
                os.environ.get("GROQ_BASE_URL"))
    pri_model = (os.environ.get("AUTOCLIP_PRIMARY_MODEL") or
                 os.environ.get("OPENAI_MODEL") or
                 os.environ.get("GROQ_MODEL"))
    pri_key = (os.environ.get("AUTOCLIP_PRIMARY_API_KEY") or
               os.environ.get("OPENAI_API_KEY") or
               os.environ.get("GROQ_API_KEY") or
               os.environ.get("GEMINI_API_KEY") or "").strip()

    legacy_base = os.environ.get("AUTOCLIP_LLM_BASE")
    legacy_model = os.environ.get("AUTOCLIP_LLM_MODEL")
    if legacy_base and legacy_base != DEFAULT_LOCAL_BASE:
        pri_base = pri_base or legacy_base
    if legacy_model and legacy_model != DEFAULT_LOCAL_MODEL:
        pri_model = pri_model or legacy_model

    if pri_base and pri_model:
        key_sig = (pri_base.rstrip("/"), pri_model)
        if key_sig not in seen:
            is_ready = bool(pri_key) or _is_local(pri_base)
            providers.append({
                "name": "Primary (Best Model)",
                "base_url": pri_base.rstrip("/"),
                "model": pri_model,
                "api_key": pri_key,
                "configured": is_ready,
                "timeout": int(os.environ.get("AUTOCLIP_PRIMARY_TIMEOUT", DEFAULT_TIMEOUT)),
            })
            seen.add(key_sig)

    # 2. Secondary / Fallback Provider (second best model)
    sec_base = (os.environ.get("AUTOCLIP_FALLBACK_BASE_URL") or
                os.environ.get("AUTOCLIP_SECONDARY_BASE_URL"))
    sec_model = (os.environ.get("AUTOCLIP_FALLBACK_MODEL") or
                 os.environ.get("AUTOCLIP_SECONDARY_MODEL"))
    sec_key = (os.environ.get("AUTOCLIP_FALLBACK_API_KEY") or
               os.environ.get("AUTOCLIP_SECONDARY_API_KEY") or "").strip()

    if sec_base and sec_model:
        key_sig = (sec_base.rstrip("/"), sec_model)
        if key_sig not in seen:
            is_ready = bool(sec_key) or _is_local(sec_base)
            providers.append({
                "name": "Secondary (Fallback Model)",
                "base_url": sec_base.rstrip("/"),
                "model": sec_model,
                "api_key": sec_key,
                "configured": is_ready,
                "timeout": int(os.environ.get("AUTOCLIP_FALLBACK_TIMEOUT", DEFAULT_TIMEOUT)),
            })
            seen.add(key_sig)

    # 3. Cloud Provider (Free LLM Cloud Server for 24/7 access)
    cloud_base = os.environ.get("AUTOCLIP_CLOUD_BASE_URL")
    cloud_model = os.environ.get("AUTOCLIP_CLOUD_MODEL") or os.environ.get("AUTOCLIP_PRIMARY_MODEL")
    cloud_key = os.environ.get("AUTOCLIP_CLOUD_API_KEY") or os.environ.get("AUTOCLIP_PRIMARY_API_KEY", "").strip()
    if cloud_base and cloud_model:
        key_sig = (cloud_base.rstrip("/"), cloud_model)
        if key_sig not in seen:
            providers.append({
                "name": "Cloud (FreeLLM 24/7)",
                "base_url": cloud_base.rstrip("/"),
                "model": cloud_model,
                "api_key": cloud_key,
                "configured": True,
                "timeout": int(os.environ.get("AUTOCLIP_CLOUD_TIMEOUT", "20")),
            })
            seen.add(key_sig)

    # 4. Local Provider (Ollama or local offline fallback)
    loc_base = os.environ.get("AUTOCLIP_LOCAL_BASE_URL", DEFAULT_LOCAL_BASE)
    loc_model = os.environ.get("AUTOCLIP_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    loc_key = os.environ.get("AUTOCLIP_LOCAL_API_KEY", "").strip()
    key_sig = (loc_base.rstrip("/"), loc_model)
    if key_sig not in seen:
        providers.append({
            "name": "Local Fallback (Ollama)",
            "base_url": loc_base.rstrip("/"),
            "model": loc_model,
            "api_key": loc_key,
            "configured": True,
            "timeout": int(os.environ.get("AUTOCLIP_LOCAL_TIMEOUT", "30")),
        })
        seen.add(key_sig)

    return providers


def _call_http(provider, payload, timeout):
    """Execute raw HTTP request to an OpenAI-compatible /chat/completions endpoint."""
    base = provider["base_url"].rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1") or base.endswith("/v1beta/openai") or base.endswith("/openai/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/chat/completions"

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AutoClip/2.0",
    }
    if provider.get("api_key"):
        headers["Authorization"] = f"Bearer {provider['api_key']}"

    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _call_provider(provider, system, user, schema=None, temperature=0.2, timeout=None):
    """Call one provider. Handles response_format fallback and retries."""
    t_out = timeout or provider.get("timeout", DEFAULT_TIMEOUT)
    payload = {
        "model": provider["model"],
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if schema is not None:
        payload["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(2):
        try:
            data = _call_http(provider, payload, t_out)
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            if schema is not None:
                parsed = _extract_json(content)
                if parsed is None:
                    raise ValueError(f"Provider returned no parseable JSON. Content: {content[:150]}")
                if isinstance(parsed, list) and isinstance(schema, dict) and len(schema) == 1:
                    single_key = list(schema.keys())[0]
                    parsed = {single_key: parsed}
                errors = []
                _validate_spec(schema, parsed, "$", errors)
                if errors:
                    raise ValueError("JSON failed schema validation: " + "; ".join(errors))
                return parsed
            parsed = _extract_json(content)
            return parsed if parsed is not None else content.strip()

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code == 400 and "response_format" in payload:
                del payload["response_format"]
                continue
            msg = f"HTTP {e.code} {e.reason}"
            if err_body:
                try:
                    ej = json.loads(err_body)
                    msg += f": {ej.get('error', {}).get('message', err_body[:200])}"
                except Exception:
                    msg += f": {err_body[:200]}"
            last_err = RuntimeError(msg)
            break

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
            last_err = e
            s_err = str(e).lower()
            if "refused" in s_err or "10061" in s_err or "timed out" in s_err or isinstance(e, TimeoutError):
                break
            if attempt == 0:
                time.sleep(1)
                continue

    raise last_err or RuntimeError("Provider call failed")


def chat(system, user, schema=None, model=None, base_url=None, api_key=None,
         temperature=0.2, timeout=None):
    """Call the LLM with automatic multi-model cascading fallback.

    Tries the Primary (best) model first, then Secondary (fallback) model, then
    Local model. If an explicit `base_url` or `model` is passed, that takes
    priority before the cascade.

    Returns parsed JSON (if schema is given) or validated response.
    """
    candidates = []

    if model or base_url:
        candidates.append({
            "name": f"Explicit ({model or 'custom'})",
            "base_url": (base_url or os.environ.get("AUTOCLIP_PRIMARY_BASE_URL", DEFAULT_LOCAL_BASE)).rstrip("/"),
            "model": model or os.environ.get("AUTOCLIP_PRIMARY_MODEL", DEFAULT_LOCAL_MODEL),
            "api_key": api_key or os.environ.get("AUTOCLIP_PRIMARY_API_KEY", ""),
            "configured": True,
            "timeout": timeout or DEFAULT_TIMEOUT,
        })

    for p in get_providers():
        sig = (p["base_url"], p["model"])
        if not any((c["base_url"], c["model"]) == sig for c in candidates):
            candidates.append(p)

    errors = []
    for prov in candidates:
        if not prov.get("configured", True):
            print(f"[AutoClip LLM] Skipping {prov['name']} ({prov['model']}): no API key in .env", flush=True)
            continue
        try:
            res = _call_provider(prov, system, user, schema=schema,
                                 temperature=temperature, timeout=timeout)
            print(f"[AutoClip LLM] Success via {prov['name']} ({prov['model']})", flush=True)
            return res
        except Exception as e:
            err_msg = str(e)
            errors.append(f"{prov['name']} [{prov['model']}]: {err_msg}")
            print(f"[AutoClip LLM] {prov['name']} ({prov['model']}) failed: {err_msg}. Cascading...", flush=True)

    raise RuntimeError("All LLM providers in cascade failed:\n  - " + "\n  - ".join(errors))


def query_cascade(user_prompt, system_prompt="You are the AI Executive Producer for YouTube channel 'Ask What?' (@askwhatt)."):
    """Convenience wrapper for conversational producer queries."""
    res = chat(system_prompt, user_prompt)
    if isinstance(res, dict):
        return res.get("content") or res.get("reply") or json.dumps(res)
    return str(res)


def test_llm():
    """Diagnostic tool to test all configured LLM providers."""
    providers = get_providers()
    print("=" * 60)
    print("AutoClip LLM Multi-Provider Cascade Status:")
    print("=" * 60)
    if not providers:
        print("No providers configured!")
        return

    test_system = "You are a health check assistant. Reply with JSON."
    test_user = "Reply with JSON: {\"status\": \"ok\", \"message\": \"AutoClip LLM ready\"}"
    test_schema = {"status": ("str", True), "message": ("str", True)}

    for idx, p in enumerate(providers, 1):
        masked_key = (p['api_key'][:6] + "..." + p['api_key'][-4:]) if len(p['api_key']) > 10 else ("(none)" if not p['api_key'] else "***")
        print(f"\n[{idx}] {p['name']}")
        print(f"    Model:      {p['model']}")
        print(f"    Base URL:   {p['base_url']}")
        print(f"    API Key:    {masked_key}")
        if not p.get("configured"):
            print("    Status:     NOT CONFIGURED (Add your free API key to .env to activate)")
            continue

        print("    Testing connection...", end=" ", flush=True)
        try:
            start_t = time.time()
            t_limit = 45 if _is_local(p['base_url']) else 15
            res = _call_provider(p, test_system, test_user, schema=test_schema, timeout=t_limit)
            elapsed = time.time() - start_t
            print(f"SUCCESS in {elapsed:.2f}s! Result: {res}")
        except Exception as e:
            print(f"FAILED: {e}")
    print("\n" + "=" * 60)