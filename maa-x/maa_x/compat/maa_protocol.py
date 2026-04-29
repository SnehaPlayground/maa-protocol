"""Compatibility shim for maa_protocol v0.2+.

Usage:
    # Old code:
    from maa_protocol import GovernanceWrapper
    # New code (drop-in replacement):
    from maa_x.compat import GovernanceWrapper
"""

# Re-export everything from the compat module
from . import *