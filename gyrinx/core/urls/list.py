from django.urls import path

from ..views import print_config, vehicle
from ..views import pack as pack_views
from ..views.list import attributes as list_attributes
from ..views.list import invitations as list_invitations
from ..views.list import skill_trees as list_skill_trees
from ..views.list import views as list_views

patterns = [
    path("lists/", list_views.ListsListView.as_view(), name="lists"),
    path("lists/new/packs", list_views.new_list_packs, name="lists-new-packs"),
    path("lists/new", list_views.new_list, name="lists-new"),
    path("list/<id>", list_views.ListDetailView.as_view(), name="list"),
    path(
        "list/<id>/perf",
        list_views.ListPerformanceView.as_view(),
        name="list-performance",
    ),
    path(
        "list/<id>/about", list_views.ListAboutDetailView.as_view(), name="list-about"
    ),
    path(
        "list/<id>/notes", list_views.ListNotesDetailView.as_view(), name="list-notes"
    ),
    path("list/<id>/archive", list_views.archive_list, name="list-archive"),
    path("list/<id>/show-stash", list_views.show_stash, name="list-show-stash"),
    path(
        "list/<id>/refresh-cost", list_views.refresh_list_cost, name="list-refresh-cost"
    ),
    path("list/<id>/pin", list_views.toggle_list_pin, name="list-pin"),
    path("list/<id>/star", list_views.toggle_list_star, name="list-star"),
    path("list/<id>/edit", list_views.edit_list, name="list-edit"),
    path("list/<id>/packs", pack_views.list_packs_manage, name="list-packs"),
    path("list/<id>/credits", list_views.edit_list_credits, name="list-credits-edit"),
    path("list/<id>/clone", list_views.clone_list, name="list-clone"),
    path(
        "list/<id>/invitations",
        list_invitations.list_invitations,
        name="list-invitations",
    ),
    path(
        "list/<id>/invitations/<invitation_id>/accept",
        list_invitations.accept_invitation,
        name="invitation-accept",
    ),
    path(
        "list/<id>/invitations/<invitation_id>/decline",
        list_invitations.decline_invitation,
        name="invitation-decline",
    ),
    path(
        "list/<id>/campaign/<campaign_id>/packs",
        list_invitations.invitation_pack_setup,
        name="invitation-pack-setup",
    ),
    path("list/<id>/vehicles/new", vehicle.new_vehicle, name="list-vehicle-new"),
    path(
        "list/<id>/vehicles/new/select",
        vehicle.vehicle_select,
        name="list-vehicle-select",
    ),
    path("list/<id>/vehicles/new/crew", vehicle.vehicle_crew, name="list-vehicle-crew"),
    path(
        "list/<id>/vehicles/new/confirm",
        vehicle.vehicle_confirm,
        name="list-vehicle-confirm",
    ),
    path("list/<id>/print", list_views.ListPrintView.as_view(), name="list-print"),
    path(
        "list/<list_id>/print-configs",
        print_config.PrintConfigIndexView.as_view(),
        name="print-config-index",
    ),
    path(
        "list/<list_id>/print-configs/new",
        print_config.print_config_create,
        name="print-config-create",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/edit",
        print_config.print_config_edit,
        name="print-config-edit",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/delete",
        print_config.print_config_delete,
        name="print-config-delete",
    ),
    path(
        "list/<list_id>/print-configs/<config_id>/print",
        print_config.print_config_print,
        name="print-config-print",
    ),
    path(
        "list/<id>/attributes",
        list_attributes.manage_list_attributes,
        name="list-attributes-manage",
    ),
    path(
        "list/<id>/attribute/<attribute_id>/edit",
        list_attributes.edit_list_attribute,
        name="list-attribute-edit",
    ),
    path(
        "list/<id>/skill-trees",
        list_skill_trees.manage_list_skill_trees,
        name="list-skill-trees-manage",
    ),
    path(
        "list/<id>/skill-trees/edit",
        list_skill_trees.edit_list_skill_trees,
        name="list-skill-trees-edit",
    ),
    path(
        "list/<id>/campaign-clones",
        list_views.ListCampaignClonesView.as_view(),
        name="list-campaign-clones",
    ),
]
