"""
Invitation-related tools and async operations for LangGraph chatbot.
Handles sending, listing, and managing company invitations.
"""
from langchain_core.tools import tool
from datetime import datetime, timedelta
import re
import sys
import os
import logging

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dash_api'))

from .helpers import run_async, _notify_chatbot_db_change, _notify_invitation_to_user

logger = logging.getLogger(__name__)


# --- Async Invitation Operations ---

async def _send_invitation_async(
    invitee_email: str,
    current_user_id: str,
    company_id: str,
    role: str = "Member"
):
    """Async implementation of send invitation."""
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.company import Company
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    
    # Validate email format using simple regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    invitee_email = invitee_email.strip()
    if not re.match(email_pattern, invitee_email):
        return f"Error: Invalid email address '{invitee_email}'. Please provide a valid email."
    
    # Get current user (must be admin)
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Check if user is admin (handle both enum and string comparison)
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if user_role != "Admin" and user_role.lower() != "admin":
        return "Error: Only admins can send invitations. Please contact your administrator."
    
    # Get company info
    company = await Company.get(company_id)
    if not company:
        return "Error: Company not found."
    
    # Check if email belongs to someone already in the company
    try:
        existing_users = await User.find({"email": invitee_email}).to_list()
        existing_user = existing_users[0] if existing_users else None
        if existing_user:
            # Check if already a member
            existing_company_ids = existing_user.get_effective_company_ids() if hasattr(existing_user, 'get_effective_company_ids') else []
            if company_id in existing_company_ids:
                return f"Error: User with email '{invitee_email}' is already a member of {company.name}."
    except Exception as e:
        logger.warning(f"Error checking existing user: {e}")
        existing_user = None
    
    # Check if invitation already exists and is pending
    try:
        status_value = InvitationStatus.PENDING.value if hasattr(InvitationStatus.PENDING, 'value') else str(InvitationStatus.PENDING)
        existing_invitations = await Invitation.find({
            "invitee_email": invitee_email,
            "company_id": company_id,
            "status": status_value
        }).to_list()
        existing_invitation = existing_invitations[0] if existing_invitations else None
    except Exception as e:
        logger.warning(f"Error checking existing invitation: {e}")
        existing_invitation = None
    
    if existing_invitation:
        return f"Error: A pending invitation has already been sent to '{invitee_email}' for {company.name}."
    
    # Validate role
    valid_roles = [r.value for r in UserRole]
    if role not in valid_roles:
        return f"Error: Invalid role '{role}'. Valid roles are: {', '.join(valid_roles)}"
    
    # Create invitation
    expires_at = datetime.utcnow() + timedelta(days=30)  # 30-day expiry
    
    new_invitation = Invitation(
        invitee_email=invitee_email,
        invitee_user_id=str(existing_user.id) if existing_user else None,
        company_id=company_id,
        company_name=company.name,
        inviter_id=current_user_id,
        inviter_name=current_user.name,
        role=role,
        status=InvitationStatus.PENDING,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    await new_invitation.insert()
    
    # Notify via WebSocket that chatbot sent an invitation (broadcasts to company)
    await _notify_chatbot_db_change(
        company_id,
        "invitation_sent",
        {"invitation_id": str(new_invitation.id), "invitee_email": invitee_email, "role": role}
    )
    
    # Also send a direct notification to the invitee user if they exist
    if existing_user:
        await _notify_invitation_to_user(
            str(existing_user.id),
            {
                "id": str(new_invitation.id),
                "invitee_email": invitee_email,
                "invitee_user_id": str(existing_user.id),
                "company_id": company_id,
                "company_name": company.name,
                "inviter_id": current_user_id,
                "inviter_name": current_user.name,
                "role": role,
                "status": "Pending",
                "created_at": new_invitation.created_at.isoformat() if new_invitation.created_at else None,
                "updated_at": new_invitation.updated_at.isoformat() if new_invitation.updated_at else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "message": f"You have been invited to join {company.name}"
            }
        )
    
    return f"""✅ **Invitation Sent Successfully!**

📧 **Invitee Email:** {invitee_email}
🏢 **Company:** {company.name}
👤 **Role:** {role}
📅 **Expires:** {expires_at.strftime('%Y-%m-%d')}

The user will receive an invitation to join your company and can accept or decline it."""


async def _list_received_invitations_async(current_user_id: str):
    """Async implementation of list received invitations."""
    from dash_api.app.models.user import User
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    
    # Get current user
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Find invitations sent to this user's email
    try:
        invitations = await Invitation.find({
            "invitee_email": current_user.email
        }).sort([("created_at", -1)]).to_list()
    except Exception as e:
        logger.warning(f"Error fetching received invitations: {e}")
        return "📭 **No Invitations**\n\nYou haven't received any company invitations yet."
    
    if not invitations:
        return "📭 **No Invitations**\n\nYou haven't received any company invitations yet."
    
    # Group by status for better display
    pending = [inv for inv in invitations if inv.status == InvitationStatus.PENDING]
    accepted = [inv for inv in invitations if inv.status == InvitationStatus.ACCEPTED]
    declined = [inv for inv in invitations if inv.status == InvitationStatus.DECLINED]
    
    result = "📬 **Your Invitations**\n\n"
    
    if pending:
        result += "🔔 **Pending Invitations:**\n"
        for inv in pending:
            expires_str = inv.expires_at.strftime("%Y-%m-%d") if inv.expires_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Expires: {expires_str})\n"
            result += f"    Sent by: {inv.inviter_name}\n"
        result += "\n"
    
    if accepted:
        result += "✅ **Accepted Invitations:**\n"
        for inv in accepted:
            joined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Joined: {joined_str})\n"
        result += "\n"
    
    if declined:
        result += "❌ **Declined Invitations:**\n"
        for inv in declined:
            declined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Declined: {declined_str})\n"
    
    return result


async def _list_sent_invitations_async(current_user_id: str, company_id: str):
    """Async implementation of list sent invitations - for admins."""
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.company import Company
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    
    # Get current user (must be admin)
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Check if user is admin (handle both enum and string comparison)
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if user_role != "Admin" and user_role.lower() != "admin":
        return "Error: Only admins can view sent invitations."
    
    # Get company info
    company = await Company.get(company_id)
    if not company:
        return "Error: Company not found."
    
    # Find invitations sent from this company
    try:
        invitations = await Invitation.find({
            "company_id": company_id
        }).sort([("created_at", -1)]).to_list()
    except Exception as e:
        logger.warning(f"Error fetching sent invitations: {e}")
        return f"📭 **No Invitations Sent**\n\nNo invitations have been sent from {company.name} yet."
    
    if not invitations:
        return f"📭 **No Invitations Sent**\n\nNo invitations have been sent from {company.name} yet."
    
    # Group by status
    pending = [inv for inv in invitations if inv.status == InvitationStatus.PENDING]
    accepted = [inv for inv in invitations if inv.status == InvitationStatus.ACCEPTED]
    declined = [inv for inv in invitations if inv.status == InvitationStatus.DECLINED]
    
    result = f"📤 **Invitations Sent from {company.name}**\n\n"
    
    if pending:
        result += f"🔔 **Pending ({len(pending)}):**\n"
        for inv in pending:
            expires_str = inv.expires_at.strftime("%Y-%m-%d") if inv.expires_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Expires: {expires_str})\n"
        result += "\n"
    
    if accepted:
        result += f"✅ **Accepted ({len(accepted)}):**\n"
        for inv in accepted:
            joined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Joined: {joined_str})\n"
        result += "\n"
    
    if declined:
        result += f"❌ **Declined ({len(declined)}):**\n"
        for inv in declined:
            declined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Declined: {declined_str})\n"
    
    return result


# --- LangGraph Invitation Tools (Sync Wrappers) ---

@tool
def send_invitation(invitee_email: str, current_user_id: str, company_id: str, role: str = "Member"):
    """Send an invitation to a user to join your company.
    ADMIN ONLY - Only administrators can send invitations.
    
    Parameters:
    - invitee_email: The email address of the person to invite (e.g., "john@example.com")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    - role: Role to assign upon acceptance - "Admin", "Member", or "Viewer" (default: "Member")
    
    Example usage:
    - "Send an invitation to samriddhi@email.com"
    - "Invite john@company.com as an Admin"
    - "Send invitation to user@example.com with Member role"
    
    Note:
    - Invitations expire after 30 days
    - The recipient will receive a notification and can accept or decline
    - User must not already be a member of your company
    """
    return run_async(_send_invitation_async(invitee_email, current_user_id, company_id, role))


@tool
def list_received_invitations(current_user_id: str):
    """List all invitations you have received from companies.
    Shows pending, accepted, and declined invitations.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    
    Example usage:
    - "Show me my invitations"
    - "What invitations have I received?"
    - "List all my pending invitations"
    """
    return run_async(_list_received_invitations_async(current_user_id))


@tool
def list_sent_invitations(current_user_id: str, company_id: str):
    """List all invitations sent from your company.
    ADMIN ONLY - Shows pending, accepted, and declined invitations.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example usage:
    - "Show me all invitations we've sent"
    - "Who have we invited to join?"
    - "List pending invitations"
    """
    return run_async(_list_sent_invitations_async(current_user_id, company_id))


# Export all invitation tools
invitation_tools = [
    send_invitation,
    list_received_invitations,
    list_sent_invitations,
]
