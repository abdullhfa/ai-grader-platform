"""Compatibility wrapper for Starlette's old and new TemplateResponse APIs."""
from __future__ import annotations

from typing import Any

from fastapi.templating import Jinja2Templates as _Jinja2Templates


class Jinja2Templates(_Jinja2Templates):
    """Accept the legacy ``(name, context)`` call shape used by this app.

    Starlette 1.0+ changed the positional order to ``(request, name, context)``.
    Keeping the adapter at the template boundary avoids fragile edits to every
    route and remains compatible with routes already using the new signature.
    """

    def TemplateResponse(self, *args: Any, **kwargs: Any):  # noqa: N802
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) > 1 else kwargs.pop("context", None)
            context = dict(context or {})
            request = kwargs.pop("request", None) or context.get("request")
            if request is None:
                raise ValueError("TemplateResponse context must include 'request'")

            positional_names = ("status_code", "headers", "media_type", "background")
            for key, value in zip(positional_names, args[2:]):
                kwargs.setdefault(key, value)
            return super().TemplateResponse(
                request=request,
                name=name,
                context=context,
                **kwargs,
            )
        return super().TemplateResponse(*args, **kwargs)
