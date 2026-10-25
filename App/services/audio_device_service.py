# services/audio_device_service.py
"""Enumerates Windows WASAPI loopback audio devices (for capturing system audio)."""

import pyaudiowpatch


class AudioDeviceService:
    @staticmethod
    def list_loopback_devices() -> list[tuple[int, str]]:
        """Returns list of (device_index, name) — WASAPI loopback only."""
        devices = []
        p = pyaudiowpatch.PyAudio()
        try:
            wasapi_index = None
            for i in range(p.get_host_api_count()):
                api = p.get_host_api_info_by_index(i)
                if "WASAPI" in api.get("name", ""):
                    wasapi_index = i
                    break
            if wasapi_index is None:
                return devices

            api_info = p.get_host_api_info_by_index(wasapi_index)
            for n in range(api_info["deviceCount"]):
                di = p.get_device_info_by_host_api_device_index(wasapi_index, n)
                if di.get("isLoopbackDevice", False):
                    devices.append((di["index"], di["name"]))
        finally:
            p.terminate()
        return devices
