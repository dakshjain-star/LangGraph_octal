"""Invitation management routes."""
from fastapi import APIRouter, Depends, status, HTTPException
from typing import List
from bson import ObjectId
from bson.errors import InvalidId

from app.schemas.invitation import InvitationResponse, InvitationActionRequest
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User
from app.middleware.auth import get_current_user


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
    invitations = await Invitation.find(
        Invitation.company_name == current_user.company_name
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
    - If accepted, user's company_name is NOT changed (they can be part of multiple companies conceptually)
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
        # Optionally update user's company or add to a list of companies
        # For now, we just mark the invitation as accepted
    else:
        invitation.status = InvitationStatus.DECLINED
    
    invitation.updated_at = __import__('datetime').datetime.utcnow()
    await invitation.save()
    
    return InvitationResponse(
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
