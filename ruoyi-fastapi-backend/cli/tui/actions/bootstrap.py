from cli.tui.actions.assembly import TuiActionRegistryBuilder
from cli.tui.actions.builders import TuiActionSpecFactory, TuiActionTemplateSupport
from cli.tui.actions.execution import TuiActionExecutionService
from cli.tui.actions.factories.cache import CacheActionTemplateFactory
from cli.tui.actions.factories.gen import GenActionTemplateFactory
from cli.tui.actions.factories.jobs import JobActionTemplateFactory
from cli.tui.actions.factories.static import StaticActionTemplateFactory
from cli.tui.actions.presentation import TuiActionPresentationService
from cli.tui.capabilities import TUI_CAPABILITY_REGISTRY

_ACTION_SPEC_FACTORY = TuiActionSpecFactory()
TUI_ACTION_EXECUTION_SERVICE = TuiActionExecutionService()

_ACTION_TEMPLATE_SUPPORT = TuiActionTemplateSupport(spec_factory=_ACTION_SPEC_FACTORY)
_JOB_ACTION_TEMPLATE_FACTORY = JobActionTemplateFactory(support=_ACTION_TEMPLATE_SUPPORT)
_CACHE_ACTION_TEMPLATE_FACTORY = CacheActionTemplateFactory(support=_ACTION_TEMPLATE_SUPPORT)
_GEN_ACTION_TEMPLATE_FACTORY = GenActionTemplateFactory(support=_ACTION_TEMPLATE_SUPPORT)
_STATIC_ACTION_TEMPLATE_FACTORY = StaticActionTemplateFactory(support=_ACTION_TEMPLATE_SUPPORT)
_ACTION_REGISTRY_BUILDER = TuiActionRegistryBuilder(
    jobs=_JOB_ACTION_TEMPLATE_FACTORY,
    cache=_CACHE_ACTION_TEMPLATE_FACTORY,
    gen=_GEN_ACTION_TEMPLATE_FACTORY,
    static=_STATIC_ACTION_TEMPLATE_FACTORY,
    spec_factory=_ACTION_SPEC_FACTORY,
)
TUI_ACTION_REGISTRY = _ACTION_REGISTRY_BUILDER.build()

TUI_ACTION_PRESENTATION_SERVICE = TuiActionPresentationService(
    capability_registry=TUI_CAPABILITY_REGISTRY,
    action_registry=TUI_ACTION_REGISTRY,
)
