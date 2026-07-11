"""crowdvision.sim — zero-hardware simulation harness.

`python -m crowdvision.sim --all` starts an embedded amqtt broker and every
sim component (5 looping feeds, a scripted kill-shot decider, a virtual gate,
and a virtual officer) so judges reproduce the full mesh with no phones.
See sim/__main__.py.
"""
