from rest_framework import serializers


class AttachmentSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    content = serializers.CharField(help_text="Raw text or Base64 encoded string")
    mimetype = serializers.CharField(max_length=100, default="application/octet-stream", required=False)
    is_base64 = serializers.BooleanField(default=False, required=False)


class SendEmailSerializer(serializers.Serializer):
    recipient = serializers.EmailField(
        required=False,
        allow_null=True,
        help_text="Single recipient email address"
    )
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=False,
        help_text="List of recipient email addresses for bulk sending"
    )
    subject = serializers.CharField(max_length=255, default="Notification from Celery Email Service")
    message = serializers.CharField(required=False, allow_blank=True, default="")
    html_message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    template = serializers.ChoiceField(
        choices=[('none', 'None'), ('welcome', 'Welcome Template'), ('notification', 'Notification Template')],
        default='none',
        required=False
    )
    context = serializers.DictField(required=False, default=dict)
    attachments = AttachmentSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        recipient = attrs.get('recipient')
        recipients = attrs.get('recipients')

        if not recipient and not recipients:
            raise serializers.ValidationError(
                "Either 'recipient' (single email) or 'recipients' (list of emails) must be provided."
            )

        # Resolve template choice to actual template path
        template_choice = attrs.get('template')
        if template_choice == 'welcome':
            attrs['template_name'] = 'emails/welcome.html'
        elif template_choice == 'notification':
            attrs['template_name'] = 'emails/notification.html'
        else:
            attrs['template_name'] = None

        return attrs

