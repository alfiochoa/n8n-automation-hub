#!/usr/bin/env python3
"""Generate sanitized workflow JSON into ./workflows. Run: python3 scripts/build_workflows.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "wf"))
from lib import write
import subs, lead, fx, triage, price, ops

OUT = os.path.join(os.path.dirname(__file__), "..", "workflows")
for w in (subs.notify(), subs.normalize(), lead.lead_intake(), fx.fx_digest(), triage.triage(),
          price.price_scraper(), ops.error_handler(), ops.health(), ops.dlq()):
    write(w, OUT)
    print("wrote", w.name)
