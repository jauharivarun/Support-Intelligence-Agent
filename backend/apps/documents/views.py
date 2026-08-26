from pathlib import Path

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.documents.models import SourceDocument
from apps.documents.serializers import DocumentUploadSerializer, SourceDocumentSerializer
from apps.users.permissions import IsAdminRole, IsInternalOrAdmin


class DocumentListView(generics.ListAPIView):
    serializer_class = SourceDocumentSerializer
    permission_classes = [IsInternalOrAdmin]
    queryset = SourceDocument.objects.all()


class DocumentUploadView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        ser = DocumentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc = ser.create_document()
        return Response(SourceDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SourceDocumentSerializer
    permission_classes = [IsAdminRole]
    queryset = SourceDocument.objects.all()

    def perform_destroy(self, instance):
        path = instance.file_path
        super().perform_destroy(instance)
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def perform_update(self, serializer):
        account_code = self.request.data.get("account_code")
        account = None
        if account_code:
            account = Account.objects.filter(account_code=account_code).first()
        serializer.save(account=account if account_code else serializer.instance.account)
