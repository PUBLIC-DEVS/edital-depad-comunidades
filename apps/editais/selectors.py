"""Configured definitions shared by analyst runtime and read-only preview."""


def active_requirement_checks(requirement):
    # Uses the prefetched collection when available; an empty list means direct check.
    return [check for check in requirement.checks.all() if check.active]
