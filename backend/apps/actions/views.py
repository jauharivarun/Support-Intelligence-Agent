from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.actions.models import Escalation, FollowUpTask, PendingAction, PendingActionStatus
from apps.accounts.models import Account
from apps.audit.models import ActionAuditLog
from apps.observability.models import ObservabilityEvent
from apps.tickets.models import Ticket
from apps.users.permissions import IsInternalOrAdmin


class PendingActionConfirmView(APIView):
    def post(self, request, pk):
        try:
            action = PendingAction.objects.get(pk=pk, user=request.user)
        except PendingAction.DoesNotExist:
            return Response({"detail": "not found"}, status=404)

        if action.status == PendingActionStatus.EXPIRED or action.expires_at < timezone.now():
            action.status = PendingActionStatus.EXPIRED
            action.save(update_fields=["status"])
            return Response(
                {"detail": "Confirmation expired", "status": "EXPIRED"},
                status=400,
            )
        if action.status != PendingActionStatus.AWAITING_CONFIRMATION:
            return Response(
                {"detail": f"Invalid status {action.status}"},
                status=400,
            )

        action.status = PendingActionStatus.CONFIRMED
        action.confirmed_at = timezone.now()
        action.save(update_fields=["status", "confirmed_at"])
        ObservabilityEvent.objects.create(
            session=action.session,
            user=request.user,
            event_type=ObservabilityEvent.EventType.ACTION_CONFIRMED,
            status="CONFIRMED",
            metadata={"pending_action_id": action.id},
        )

        try:
            result = _execute(action, request.user)
            action.status = PendingActionStatus.EXECUTED
            action.executed_at = timezone.now()
            action.save(update_fields=["status", "executed_at"])
            ActionAuditLog.objects.create(
                pending_action=action,
                user=request.user,
                action_type=action.action_type,
                request_payload=action.payload,
                result=result,
                status="EXECUTED",
            )
            ObservabilityEvent.objects.create(
                session=action.session,
                user=request.user,
                event_type=ObservabilityEvent.EventType.ACTION_EXECUTED,
                status="EXECUTED",
                metadata={"pending_action_id": action.id, "result": result},
            )
            return Response({"status": "EXECUTED", "result": result})
        except Exception as e:
            action.status = PendingActionStatus.FAILED
            action.save(update_fields=["status"])
            ActionAuditLog.objects.create(
                pending_action=action,
                user=request.user,
                action_type=action.action_type,
                request_payload=action.payload,
                result={"error": str(e)},
                status="FAILED",
            )
            ObservabilityEvent.objects.create(
                session=action.session,
                user=request.user,
                event_type=ObservabilityEvent.EventType.ACTION_FAILED,
                status="FAILED",
                metadata={"pending_action_id": action.id, "error": str(e)},
            )
            return Response({"status": "FAILED", "detail": str(e)}, status=500)


class PendingActionCancelView(APIView):
    def post(self, request, pk):
        try:
            action = PendingAction.objects.get(pk=pk, user=request.user)
        except PendingAction.DoesNotExist:
            return Response({"detail": "not found"}, status=404)
        if action.status != PendingActionStatus.AWAITING_CONFIRMATION:
            return Response({"detail": f"Invalid status {action.status}"}, status=400)
        action.status = PendingActionStatus.CANCELLED
        action.save(update_fields=["status"])
        ActionAuditLog.objects.create(
            pending_action=action,
            user=request.user,
            action_type=action.action_type,
            request_payload=action.payload,
            result={"cancelled": True},
            status="CANCELLED",
        )
        return Response({"status": "CANCELLED"})


class PendingActionDetailView(APIView):
    def get(self, request, pk):
        try:
            action = PendingAction.objects.get(pk=pk, user=request.user)
        except PendingAction.DoesNotExist:
            return Response({"detail": "not found"}, status=404)
        return Response(
            {
                "id": action.id,
                "action_type": action.action_type,
                "payload": action.payload,
                "reason": action.reason,
                "status": action.status,
                "expires_at": action.expires_at,
            }
        )


def _execute(action: PendingAction, user) -> dict:
    payload = action.payload or {}
    if action.action_type == "CREATE_ESCALATION":
        account = None
        ticket = None
        if payload.get("account_id"):
            account = Account.objects.filter(account_code=payload["account_id"]).first()
        if payload.get("ticket_id"):
            ticket = Ticket.objects.filter(ticket_id=payload["ticket_id"]).first()
        esc = Escalation.objects.create(
            ticket=ticket,
            account=account,
            severity=payload.get("severity", "P2"),
            reason=payload.get("reason", action.reason),
            created_by=user,
        )
        return {"escalation_id": esc.id, "status": esc.status}
    if action.action_type == "CREATE_FOLLOW_UP":
        account = None
        ticket = None
        if payload.get("account_id"):
            account = Account.objects.filter(account_code=payload["account_id"]).first()
        if payload.get("ticket_id"):
            ticket = Ticket.objects.filter(ticket_id=payload["ticket_id"]).first()
        task = FollowUpTask.objects.create(
            account=account,
            ticket=ticket,
            title=payload.get("title", "Follow-up"),
            description=payload.get("description", ""),
            created_by=user,
        )
        return {"follow_up_id": task.id, "status": task.status}
    raise ValueError(f"Unknown action type {action.action_type}")
