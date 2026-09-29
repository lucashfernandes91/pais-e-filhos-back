# Backup e retenção

Backups de banco e mídia devem ser criptografados antes de sair do servidor,
com uma chave gerenciada fora da máquina (KMS ou cofre de segredos). A chave
não deve ser gravada no repositório, no banco ou no mesmo diretório do backup.

Use `ATTACHMENT_RETENTION_DAYS` e `BACKUP_RETENTION_DAYS` na configuração de
produção. Execute `python manage.py cleanup_uploads` diariamente e agende a
expiração dos backups no provedor de armazenamento.

O comando remove arquivos de `MEDIA_ROOT/attachments` que não possuem registro
em `Message` e remove anexos fora da retenção. O fluxo de exclusão de conta
também remove os anexos vinculados à conta conforme a janela aprovada.
