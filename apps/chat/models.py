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

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='legal_acceptances')
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
        return f"{self.user.username} aceitou {self.terms_version}/{self.privacy_version}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to='attachments/', null=True, blank=True)
    attachment_type = models.CharField(max_length=20, blank=True)  # image, document, etc.
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

    class Meta:
        ordering = ['event_date']

    def __str__(self):
        return f"{self.title} ({self.event_date})"


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

    child = models.OneToOneField(Child, on_delete=models.CASCADE, related_name='legal_declaration')
    declared_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='child_legal_declarations')
    declaration_version = models.CharField(max_length=20)
    declared_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='android')

    class Meta:
        ordering = ['-declared_at']

    def __str__(self):
        return f"Child declaration {self.child_id} by {self.declared_by.username}"
