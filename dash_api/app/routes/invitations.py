"""Invitation management routes."""
from fastapi import APIRouter, Depends, status, HTTPException
from typing import List
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime

from app.schemas.invitation import InvitationResponse, InvitationActionRequest
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User, UserRole
from app.middleware.auth import get_current_user
from app.services.websocket import notify_invitation_response, notify_user_joined


def validate_object_id(id_str: str) -> ObjectId:
    """Validate and convert string to ObjectId."""
    if not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid invitation ID format: {id_str}"
        )
    return ObjectId(id_str)

router = APIRouter()


@router.get(
    "/sent",
    response_model=List[InvitationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get sent invitations",
    description="Get all invitations sent by the current user's company"
)
async def get_sent_invitations(
    current_user: User = Depends(get_current_user)
):
    """
    Get all invitations sent by the admin of the current company.
    Only returns pending invitations.
    """
    effective_company_id = current_user.get_effective_company_id()
    if not effective_company_id:
        return []
    
    invitations = await Invitation.find(
        Invitation.company_id == effective_company_id
    ).to_list()
    
    return [
        InvitationResponse(
            id=str(inv.id),
            invitee_email=inv.invitee_email,
            invitee_user_id=inv.invitee_user_id,
            company_name=inv.company_name,
            company_id=inv.company_id,
            inviter_id=inv.inviter_id,
            inviter_name=inv.inviter_name,
            role=inv.role,
            status=inv.status,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            expires_at=inv.expires_at
        )
        for inv in invitations
    ]


@router.get(
    "/received",
    response_model=List[InvitationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get received invitations",
    description="Get all invitations received by the current user"
)
async def get_received_invitations(
    current_user: User = Depends(get_current_user)
):
    """
    Get all invitations received by the current user.
    """
    invitations = await Invitation.find(
        Invitation.invitee_email == current_user.email
    ).to_list()
    
    return [
        InvitationResponse(
            id=str(inv.id),
            invitee_email=inv.invitee_email,
            invitee_user_id=inv.invitee_user_id,
            company_name=inv.company_name,
            company_id=inv.company_id,
            inviter_id=inv.inviter_id,
            inviter_name=inv.inviter_name,
            role=inv.role,
            status=inv.status,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            expires_at=inv.expires_at
        )
        for inv in invitations
    ]


@router.post(
    "/{invitation_id}/respond",
    response_model=InvitationResponse,
    status_code=status.HTTP_200_OK,
    summary="Respond to invitation",
    description="Accept or decline an invitation"
)
async def respond_to_invitation(
    invitation_id: str,
    action: InvitationActionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Accept or decline an invitation.
    - If accepted, user's company_id and company_name are updated to join the new company
    - The invitation status is updated
    """
    obj_id = validate_object_id(invitation_id)
    
    invitation = await Invitation.find_one(Invitation.id == obj_id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    if invitation.invitee_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not for you"
        )
    
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation has already been {invitation.status.value.lower()}"
        )
    
    if action.action == "accept":
        invitation.status = InvitationStatus.ACCEPTED
        # Add the new company to user's list (don't replace existing companies)
        if invitation.company_id not in current_user.company_ids:
            current_user.company_ids.append(invitation.company_id)
        if invitation.company_name not in current_user.company_names:
            current_user.company_names.append(invitation.company_name)
        # Set the new company as the current active company
        current_user.current_company_id = invitation.company_id
        current_user.current_company_name = invitation.company_name
        # Set the role from the invitation
        current_user.role = UserRole(invitation.role) if invitation.role in [r.value for r in UserRole] else UserRole.MEMBER
        current_user.updated_at = datetime.utcnow()
        await current_user.save()
    else:
        invitation.status = InvitationStatus.DECLINED
    
    invitation.updated_at = datetime.utcnow()
    await invitation.save()
    
    invitation_response = InvitationResponse(
        id=str(invitation.id),
        invitee_email=invitation.invitee_email,
        invitee_user_id=invitation.invitee_user_id,
        company_name=invitation.company_name,
        company_id=invitation.company_id,
        inviter_id=invitation.inviter_id,
        inviter_name=invitation.inviter_name,
        role=invitation.role,
        status=invitation.status,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        expires_at=invitation.expires_at
    )
    
    # Send WebSocket notification to inviter about the response
    invitation_data = invitation_response.model_dump()
    # Convert enum to string value for JSON serialization
    if invitation_data.get('status'):
        invitation_data['status'] = invitation_data['status'].value if hasattr(invitation_data['status'], 'value') else str(invitation_data['status'])
    if invitation_data.get('created_at'):
        invitation_data['created_at'] = invitation_data['created_at'].isoformat() if hasattr(invitation_data['created_at'], 'isoformat') else str(invitation_data['created_at'])
    if invitation_data.get('updated_at'):
        invitation_data['updated_at'] = invitation_data['updated_at'].isoformat() if hasattr(invitation_data['updated_at'], 'isoformat') else str(invitation_data['updated_at'])
    if invitation_data.get('expires_at'):
        invitation_data['expires_at'] = invitation_data['expires_at'].isoformat() if hasattr(invitation_data['expires_at'], 'isoformat') else str(invitation_data['expires_at'])
    
    await notify_invitation_response(invitation_data, invitation.inviter_id, action.action)
    
    # If user accepted, notify all company members that a new user joined
    if action.action == "accept":
        user_data = {
            "id": str(current_user.id),
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
            "avatar_url": current_user.avatar_url,
            "status": current_user.status.value if hasattr(current_user.status, 'value') else str(current_user.status),
        }
        await notify_user_joined(user_data, invitation.company_id)
    
    return invitation_response


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke/Delete invitation",
    description="Revoke a sent invitation (admin) or delete a received invitation"
)
async def delete_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete/revoke an invitation.
    - Admins can revoke invitations they sent
    - Users can delete invitations they received
    """
    obj_id = validate_object_id(invitation_id)
    
    invitation = await Invitation.find_one(Invitation.id == obj_id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    # Check if user has permission to delete
    is_sender = invitation.inviter_id == str(current_user.id)
    is_receiver = invitation.invitee_email == current_user.email
    
    if not (is_sender or is_receiver):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this invitation"
        )
    
    await invitation.delete()
    
    return {"message": "Invitation deleted successfully"}
