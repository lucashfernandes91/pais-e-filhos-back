from django.contrib.auth.models import User
from django.db import models

class Conversation(models.Model):
    participants = models.ManyToManyField(User)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conversation {self.id}"


class ConversationInvite(models.Model):
    """Convite para o segundo responsável entrar na conversa.

    Apenas um convite pendente por conversa: gerar um novo apaga o anterior.
    """

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='invites')
    code = models.CharField(max_length=12, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_invites'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Invite {self.code} → Conversation {self.conversation_id}"


class PasswordResetCode(models.Model):
    """Código de 6 dígitos para redefinição de senha.

    Apenas o código mais recente não usado vale; pedidos anteriores
    ficam registrados para o rate limit por janela.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Reset code for {self.user.username}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coparent_profile')
    birth_date = models.DateField()
    email_verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile {self.user.username}"


class EmailVerificationCode(models.Model):
    """Código de 6 dígitos para confirmar o e-mail da conta.

    Mesmo contrato do PasswordResetCode: só o mais recente não usado vale.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Email verification for {self.user.username}"


class LegalAcceptance(models.Model):
    SOURCE_CHOICES = [
        ('android', 'Android'),
        ('web', 'Web'),
        ('manual', 'Manual'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legal_acceptances',
    )
    terms_version = models.CharField(max_length=20)
    privacy_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='android')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'terms_version', 'privacy_version'],
                name='unique_user_legal_versions',
            ),
        ]
        ordering = ['-accepted_at']

    def __str__(self):
        user_label = self.user.username if self.user_id else 'conta excluída'
        return f"{user_label} aceitou {self.terms_version}/{self.privacy_version}"


class Message(models.Model):
    ATTACHMENT_PENDING = 'pending'
    ATTACHMENT_APPROVED = 'approved'
    ATTACHMENT_QUARANTINED = 'quarantined'
    ATTACHMENT_STATUS_CHOICES = [
        (ATTACHMENT_PENDING, 'Pendente'),
        (ATTACHMENT_APPROVED, 'Aprovado'),
        (ATTACHMENT_QUARANTINED, 'Em quarentena'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to='attachments/', null=True, blank=True)
    attachment_type = models.CharField(max_length=20, blank=True)  # image, document, etc.
    attachment_size = models.PositiveBigIntegerField(default=0)
    attachment_sha256 = models.CharField(max_length=64, blank=True)
    attachment_status = models.CharField(
        max_length=20,
        choices=ATTACHMENT_STATUS_CHOICES,
        default=ATTACHMENT_APPROVED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content[:20] if self.content else f'Attachment {self.id}'

class Event(models.Model):
    CUSTODY = 'CUSTODY'
    SCHOOL = 'SCHOOL'
    MEDICAL = 'MEDICAL'
    OTHER = 'OTHER'

    TYPE_CHOICES = [
        (CUSTODY, 'Custódia'),
        (SCHOOL, 'Escola'),
        (MEDICAL, 'Médico'),
        (OTHER, 'Outro'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    event_date = models.DateTimeField()
    event_date_end = models.DateTimeField(null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['event_date']

    def __str__(self):
        return f"{self.title} ({self.event_date})"


class EventChange(models.Model):
    CREATED = 'CREATED'
    UPDATED = 'UPDATED'
    DELETED = 'DELETED'

    ACTION_CHOICES = [
        (CREATED, 'Criado'),
        (UPDATED, 'Editado'),
        (DELETED, 'Excluído'),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='changes',
    )
    event_id_snapshot = models.PositiveIntegerField()
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='event_changes',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='event_changes',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    event_title = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.get_action_display()}: {self.event_title}"


class MessageRead(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    reader = models.ForeignKey(User, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'reader')

    def __str__(self):
        return f"{self.reader.username} leu {self.message.id}"

class DeviceToken(models.Model):
    """Um registro por aparelho: o mesmo usuário pode ter vários devices.

    O token FCM identifica o aparelho; trocar de conta no mesmo aparelho
    reatribui o token ao novo usuário.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.TextField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} device token"

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.title} → {self.recipient.username}"


class Child(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='children')
    name = models.CharField(max_length=100)
    birth_date = models.DateField()
    photo = models.ImageField(upload_to='children_photos/', null=True, blank=True)
    has_custody = models.BooleanField(default=False)
    custody_holder = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children_under_custody',
    )
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ChildLegalDeclaration(models.Model):
    SOURCE_CHOICES = [
        ('android', 'Android'),
        ('web', 'Web'),
        ('manual', 'Manual'),
    ]

    child = models.OneToOneField(
        Child,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legal_declaration',
    )
    declared_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_legal_declarations',
    )
    declaration_version = models.CharField(max_length=20)
    declared_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='android')

    class Meta:
        ordering = ['-declared_at']

    def __str__(self):
        child = self.child_id if self.child_id else 'dados removidos'
        declarant = self.declared_by.username if self.declared_by_id else 'conta excluída'
        return f"Child declaration {child} by {declarant}"


class AccountDeletionCode(models.Model):
    email_digest = models.CharField(max_length=64, db_index=True)
    code_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class AccountDeletionRequest(models.Model):
    PENDING = 'pending'
    COMPLETED = 'completed'
    STATUS_CHOICES = [
        (PENDING, 'Pendente'),
        (COMPLETED, 'Concluído'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='account_deletion_request',
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    delete_after = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
