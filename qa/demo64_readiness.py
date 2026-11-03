"""Bounded state polling; never accept elapsed time or an auxiliary hint."""
from pathlib import Path
import time
PROBE=Path(__file__).with_suffix('.js')

def wait_ready(page, expected, timeout_ms=15000):
    end=time.monotonic()+timeout_ms/1000
    state=None
    while time.monotonic()<end:
        state=page.evaluate("e=>Promise.race([window.__epiTechnicalProbe(e),new Promise(resolve=>setTimeout(()=>resolve({ready:false,checks:{probe_timeout:false}}),1000))])",expected)
        if state['ready']:return state
        # A polling interval is not an acceptance condition; every iteration checks actual state.
        page.wait_for_timeout(20)
    raise AssertionError('CURRENT_IMAGE_READINESS_TIMEOUT '+str(state))
