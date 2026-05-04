from django.contrib.auth.models import User
from django.db import models

class Conversation(models.Model):
    participants = models.ManyToManyField(User)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conversation {self.id}"

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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='device_token')
    token = models.TextField()
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
    birth_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name