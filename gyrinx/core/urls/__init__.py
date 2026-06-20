from .campaign import patterns as campaign_patterns
from .fighter import patterns as fighter_patterns
from .list import patterns as list_patterns
from .misc import patterns as misc_patterns
from .pack import patterns as pack_patterns

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]
#
# This module is the includer for the per-domain url submodules. Each submodule
# exports a plain ``patterns`` list (no ``app_name``); they are concatenated here
# under the single ``core`` namespace so every route name resolves unchanged.

app_name = "core"
urlpatterns = (
    misc_patterns + list_patterns + fighter_patterns + campaign_patterns + pack_patterns
)
