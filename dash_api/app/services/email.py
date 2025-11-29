"""Email service for sending emails via SMTP."""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from jinja2 import Template
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending emails."""
    
    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """Send an email via SMTP."""
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            message["To"] = to_email
            message["Subject"] = subject
            
            # Add text and HTML parts
            if text_content:
                part1 = MIMEText(text_content, "plain")
                message.attach(part1)
            
            part2 = MIMEText(html_content, "html")
            message.attach(part2)
            
            # Send email
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                use_tls=settings.smtp_use_tls,
            )
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    @staticmethod
    async def send_invitation_email(
        to_email: str,
        to_name: str,
        inviter_name: str,
        company_name: str,
        invitation_link: str
    ) -> bool:
        """Send user invitation email."""
        subject = f"{inviter_name} invited you to join {company_name} on Dash SaaS"
        
        html_template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4F46E5; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
                .content { background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }
                .button { display: inline-block; padding: 12px 30px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                .footer { text-align: center; margin-top: 20px; color: #666; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>You're Invited!</h1>
                </div>
                <div class="content">
                    <p>Hi {{ to_name }},</p>
                    <p><strong>{{ inviter_name }}</strong> has invited you to join <strong>{{ company_name }}</strong> on Dash SaaS.</p>
                    <p>Dash SaaS is a powerful project and task management platform that helps teams collaborate effectively.</p>
                    <p>Click the button below to accept the invitation and create your account:</p>
                    <center>
                        <a href="{{ invitation_link }}" class="button">Accept Invitation</a>
                    </center>
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p style="word-break: break-all;">{{ invitation_link }}</p>
                    <p>This invitation will expire in 7 days.</p>
                    <p>Best regards,<br>The Dash SaaS Team</p>
                </div>
                <div class="footer">
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        html_content = html_template.render(
            to_name=to_name,
            inviter_name=inviter_name,
            company_name=company_name,
            invitation_link=invitation_link
        )
        
        text_content = f"""
        Hi {to_name},
        
        {inviter_name} has invited you to join {company_name} on Dash SaaS.
        
        Click the link below to accept the invitation:
        {invitation_link}
        
        This invitation will expire in 7 days.
        
        Best regards,
        The Dash SaaS Team
        """
        
        return await EmailService.send_email(to_email, subject, html_content, text_content)
    
    @staticmethod
    async def send_password_reset_email(
        to_email: str,
        to_name: str,
        reset_link: str
    ) -> bool:
        """Send password reset email."""
        subject = "Reset Your Dash SaaS Password"
        
        html_template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4F46E5; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
                .content { background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }
                .button { display: inline-block; padding: 12px 30px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                .footer { text-align: center; margin-top: 20px; color: #666; font-size: 12px; }
                .warning { background-color: #FEF3C7; padding: 15px; border-left: 4px solid #F59E0B; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Reset Your Password</h1>
                </div>
                <div class="content">
                    <p>Hi {{ to_name }},</p>
                    <p>We received a request to reset your password for your Dash SaaS account.</p>
                    <p>Click the button below to reset your password:</p>
                    <center>
                        <a href="{{ reset_link }}" class="button">Reset Password</a>
                    </center>
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p style="word-break: break-all;">{{ reset_link }}</p>
                    <div class="warning">
                        <strong>⚠️ Security Notice:</strong>
                        <p>This password reset link will expire in 24 hours. If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
                    </div>
                    <p>Best regards,<br>The Dash SaaS Team</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        html_content = html_template.render(
            to_name=to_name,
            reset_link=reset_link
        )
        
        text_content = f"""
        Hi {to_name},
        
        We received a request to reset your password for your Dash SaaS account.
        
        Click the link below to reset your password:
        {reset_link}
        
        This link will expire in 24 hours.
        
        If you didn't request a password reset, please ignore this email.
        
        Best regards,
        The Dash SaaS Team
        """
        
        return await EmailService.send_email(to_email, subject, html_content, text_content)


from typing import Optional

# Convenience functions
async def send_invitation_email(
    to_email: str,
    to_name: str,
    inviter_name: str,
    company_name: str,
    invitation_link: str
) -> bool:
    """Send invitation email."""
    return await EmailService.send_invitation_email(
        to_email, to_name, inviter_name, company_name, invitation_link
    )


async def send_password_reset_email(
    to_email: str,
    to_name: str,
    reset_link: str
) -> bool:
    """Send password reset email."""
    return await EmailService.send_password_reset_email(to_email, to_name, reset_link)
