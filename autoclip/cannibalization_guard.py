"""
AutoClip Cannibalization Guard & Upload Pacing Optimizer
Protects active surging Shorts from being choked by premature new uploads.
"""

import time
import datetime
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Tuple

class CannibalizationGuard:
    """Monitors channel upload velocity and prevents algorithmic cannibalization."""

    MIN_HOURS_BETWEEN_SHORTS = 6.0    # Absolute minimum spacing
    SURGE_HOURLY_VELOCITY_FLOOR = 150 # Views/hr threshold considered 'active testing'

    @staticmethod
    def inspect_upload_window(channel_id: str = None, last_upload_dt: datetime.datetime = None, current_velocity_hr: int = 0) -> Tuple[bool, datetime.datetime, str]:
        """
        Determines whether it is safe to publish now or if it should be scheduled later.
        Returns: (can_publish_now, recommended_schedule_dt, reason)
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # If last upload time is known
        if last_upload_dt:
            hours_since_last = (now - last_upload_dt).total_seconds() / 3600.0
            
            # Rule 1: Previous video is in active viral surge wave
            if hours_since_last < 8.0 and current_velocity_hr >= CannibalizationGuard.SURGE_HOURLY_VELOCITY_FLOOR:
                # Schedule for next US peak window (8-12 hours later)
                delay_hours = max(6.0, 10.0 - hours_since_last)
                target_dt = now + datetime.timedelta(hours=delay_hours)
                reason = (
                    f"Previous upload is actively surging ({current_velocity_hr} views/hr, {hours_since_last:.1f}h ago). "
                    f"Holding upload to prevent algorithmic cannibalization. Scheduled for: {target_dt.strftime('%b %d, %I:%M %p UTC')}."
                )
                return False, target_dt, reason

            # Rule 2: Minimum safe buffer
            if hours_since_last < CannibalizationGuard.MIN_HOURS_BETWEEN_SHORTS:
                delay_hours = CannibalizationGuard.MIN_HOURS_BETWEEN_SHORTS - hours_since_last
                target_dt = now + datetime.timedelta(hours=delay_hours)
                reason = (
                    f"Previous upload was only {hours_since_last:.1f}h ago. "
                    f"Enforcing minimum {CannibalizationGuard.MIN_HOURS_BETWEEN_SHORTS}h spacing buffer. Scheduled for: {target_dt.strftime('%b %d, %I:%M %p UTC')}."
                )
                return False, target_dt, reason

        # Safe to publish or schedule for immediate prime-time
        reason = "Channel is clear for new upload. No active surge conflict detected."
        return True, now, reason
