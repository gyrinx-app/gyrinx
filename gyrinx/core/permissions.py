"""
Permission decorators and utilities for views.

This module provides decorators and utilities to handle common permission
patterns in views, reducing code duplication.
"""
from functools import wraps
from typing import Callable, Optional, Type

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Model, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse


def requires_owner(
    model: Type[Model],
    lookup_field: str = "id",
    url_kwarg: Optional[str] = None,
    redirect_view: Optional[str] = None,
    message: Optional[str] = None,
) -> Callable:
    """
    Decorator that checks if the requesting user owns the object.
    
    Args:
        model: The Django model class to query
        lookup_field: The field to lookup the object by (default: 'id')
        url_kwarg: The URL kwarg name (defaults to lookup_field)
        redirect_view: View name to redirect to on permission failure
        message: Custom error message on permission failure
        
    Example:
        @requires_owner(List)
        def edit_list(request, id):
            # request.resolved_object will contain the List instance
            list_ = request.resolved_object
            ...
            
        @requires_owner(Campaign, redirect_view='core:campaigns')
        def edit_campaign(request, campaign_id):
            campaign = request.resolved_object
            ...
    """
    if url_kwarg is None:
        url_kwarg = lookup_field
        
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request: HttpRequest, **kwargs):
            lookup_value = kwargs.get(url_kwarg)
            if lookup_value is None:
                raise ValueError(f"URL kwarg '{url_kwarg}' not found in view kwargs")
                
            # Get the object and check ownership
            obj = get_object_or_404(
                model, 
                **{lookup_field: lookup_value, 'owner': request.user}
            )
            
            # Attach the object to the request for use in the view
            request.resolved_object = obj
            
            return view_func(request, **kwargs)
            
        return wrapped_view
    return decorator


def requires_list_or_campaign_owner(
    lookup_field: str = "id",
    url_kwarg: Optional[str] = None,
    redirect_view: str = 'core:lists',
    message: str = "You don't have permission to access this resource.",
) -> Callable:
    """
    Decorator that checks if the user owns the list OR the campaign it belongs to.
    
    This is specifically for List objects where campaign owners also have permissions.
    
    Args:
        lookup_field: The field to lookup the list by (default: 'id')
        url_kwarg: The URL kwarg name (defaults to lookup_field)
        redirect_view: View name to redirect to on permission failure
        message: Error message on permission failure
        
    Example:
        @requires_list_or_campaign_owner()
        def edit_list_credits(request, id):
            list_ = request.resolved_object
            ...
    """
    if url_kwarg is None:
        url_kwarg = lookup_field
        
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request: HttpRequest, **kwargs):
            from gyrinx.core.models.list import List
            
            lookup_value = kwargs.get(url_kwarg)
            if lookup_value is None:
                raise ValueError(f"URL kwarg '{url_kwarg}' not found in view kwargs")
                
            # Get list with complex permission check
            list_obj = get_object_or_404(
                List.objects.filter(
                    Q(owner=request.user) | Q(campaign__owner=request.user),
                    **{lookup_field: lookup_value}
                )
            )
            
            # Additional validation if needed
            if list_obj.owner != request.user:
                if not (list_obj.campaign and list_obj.campaign.owner == request.user):
                    messages.error(request, message)
                    return HttpResponseRedirect(
                        reverse(redirect_view, args=(list_obj.id,))
                    )
            
            request.resolved_object = list_obj
            return view_func(request, **kwargs)
            
        return wrapped_view
    return decorator


def requires_related_owner(
    parent_model: Type[Model],
    child_model: Type[Model],
    parent_lookup: str = "id",
    child_lookup: str = "id",
    parent_url_kwarg: Optional[str] = None,
    child_url_kwarg: Optional[str] = None,
    parent_field: Optional[str] = None,
    redirect_view: Optional[str] = None,
) -> Callable:
    """
    Decorator for views that need to check ownership of related objects.
    
    Common pattern: Check list ownership, then check fighter ownership.
    
    Args:
        parent_model: The parent model (e.g., List)
        child_model: The child model (e.g., ListFighter)
        parent_lookup: Field to lookup parent by (default: 'id')
        child_lookup: Field to lookup child by (default: 'id')  
        parent_url_kwarg: URL kwarg for parent (defaults to parent_lookup)
        child_url_kwarg: URL kwarg for child (defaults to child_lookup)
        parent_field: Field name on child that references parent (auto-detected if None)
        redirect_view: View to redirect to on permission failure
        
    Example:
        @requires_related_owner(List, ListFighter, 
                               parent_url_kwarg='id', 
                               child_url_kwarg='fighter_id')
        def edit_fighter(request, id, fighter_id):
            list_ = request.resolved_parent
            fighter = request.resolved_object
            ...
    """
    if parent_url_kwarg is None:
        parent_url_kwarg = parent_lookup
    if child_url_kwarg is None:
        child_url_kwarg = child_lookup
        
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request: HttpRequest, **kwargs):
            # Get parent object
            parent_value = kwargs.get(parent_url_kwarg)
            if parent_value is None:
                raise ValueError(f"URL kwarg '{parent_url_kwarg}' not found")
                
            parent_obj = get_object_or_404(
                parent_model,
                **{parent_lookup: parent_value, 'owner': request.user}
            )
            
            # Auto-detect parent field if not specified
            if parent_field is None:
                # Try common patterns
                parent_name = parent_model.__name__.lower()
                possible_fields = [parent_name, f'{parent_name}_id']
                field_name = None
                for field in possible_fields:
                    if hasattr(child_model, field):
                        field_name = field
                        break
                if field_name is None:
                    raise ValueError(
                        f"Could not auto-detect parent field on {child_model.__name__}"
                    )
            else:
                field_name = parent_field
                
            # Get child object
            child_value = kwargs.get(child_url_kwarg)
            if child_value is None:
                raise ValueError(f"URL kwarg '{child_url_kwarg}' not found")
                
            child_obj = get_object_or_404(
                child_model,
                **{
                    child_lookup: child_value,
                    field_name: parent_obj,
                    'owner': parent_obj.owner
                }
            )
            
            # Attach both objects to request
            request.resolved_parent = parent_obj
            request.resolved_object = child_obj
            
            return view_func(request, **kwargs)
            
        return wrapped_view
    return decorator


def public_or_owner(
    model: Type[Model],
    lookup_field: str = "id",
    url_kwarg: Optional[str] = None,
) -> Callable:
    """
    Decorator for views that allow public access OR owner access.
    
    No login required, but request.is_owner will be set to indicate ownership.
    
    Args:
        model: The Django model class
        lookup_field: Field to lookup by (default: 'id')
        url_kwarg: URL kwarg name (defaults to lookup_field)
        
    Example:
        @public_or_owner(List)
        def view_list(request, id):
            list_ = request.resolved_object
            if request.is_owner:
                # Show owner-specific controls
                ...
    """
    if url_kwarg is None:
        url_kwarg = lookup_field
        
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request: HttpRequest, **kwargs):
            lookup_value = kwargs.get(url_kwarg)
            if lookup_value is None:
                raise ValueError(f"URL kwarg '{url_kwarg}' not found")
                
            obj = get_object_or_404(model, **{lookup_field: lookup_value})
            
            # Check ownership
            request.is_owner = (
                request.user.is_authenticated and 
                hasattr(obj, 'owner') and 
                obj.owner == request.user
            )
            request.resolved_object = obj
            
            return view_func(request, **kwargs)
            
        return wrapped_view
    return decorator