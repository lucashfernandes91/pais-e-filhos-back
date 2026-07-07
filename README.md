# Pais e Filhos - Backend

Sistema de comunicação e coordenação para co-pais, facilitando a troca de mensagens, compartilhamento de eventos e documentação relacionada a filhos.

## 🎯 Funcionalidades

- **Autenticação JWT**: Registro e login com tokens JWT seguros
- **Conversas Privadas**: Mensagens em tempo real entre usuários
- **Compartilhamento de Anexos**: Envio de imagens, documentos e arquivos
- **Eventos**: Criação e acompanhamento de eventos (custódia, escola, médico, etc.)
- **Notificações**: Sistema de notificações via Firebase
- **Perfis de Usuário**: Gerenciamento de dados pessoais e de filhos
- **Geração de PDFs**: Exportação de conversas e documentos
- **WebSockets**: Comunicação em tempo real via Channels

## 🚀 Início Rápido

### Pré-requisitos

- Python 3.14+
- Django 6.0.4+
- PostgreSQL (recomendado) ou SQLite

### Instalação

1. Clone o repositório:
```bash
git clone <repo-url>
cd backend
```

2. Crie um ambiente virtual:
```bash
python -m venv .venv
```

3. Ative o ambiente virtual:

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

4. Instale as dependências:
```bash
pip install -e .
```

### Configuração

1. Configure as variáveis de ambiente (criar arquivo `.env`):
```
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
FIREBASE_PROJECT_ID=your-firebase-project-id
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

2. Execute as migrações:
```bash
python manage.py migrate
```

3. Crie um superusuário (opcional):
```bash
python manage.py createsuperuser
```

### Executando o Servidor

**Desenvolvimento com Django:**
```bash
python manage.py runserver
```

**Desenvolvimento com Daphne (para WebSockets):**
```bash
daphne -b 0.0.0.0 -p 8000 core.asgi:application
```

O servidor rodará em `http://localhost:8000`

## 📦 Dependências

| Pacote | Versão | Descrição |
|--------|--------|-----------|
| Django | >=6.0.4 | Framework web |
| Django REST Framework | >=3.17.1 | API RESTful |
| djangorestframework-simplejwt | >=5.5.1 | Autenticação JWT |
| django-cors-headers | >=4.3.0 | CORS |
| firebase-admin | >=6.1.0 | Firebase SDK |
| reportlab | >=4.0.0 | Geração de PDFs |
| channels | >=4.2.0 | WebSockets |
| daphne | >=4.0.0 | ASGI server |

## 📁 Estrutura do Projeto

```
backend/
├── apps/
│   └── chat/
│       ├── models.py          # Modelos de dados
│       ├── views.py           # Endpoints da API
│       ├── serializers.py      # Serializadores
│       ├── consumers.py        # Consumers WebSocket
│       ├── urls.py            # Rotas
│       ├── signals.py         # Sinais Django
│       └── migrations/        # Migrações do banco
├── core/
│   ├── settings.py            # Configurações Django
│   ├── asgi.py                # ASGI config
│   ├── wsgi.py                # WSGI config
│   ├── auth_views.py          # Views de autenticação
│   ├── pdf_generator.py       # Gerador de PDFs
│   ├── firebase_helpers.py    # Helpers Firebase
│   └── error_handler.py       # Tratamento de erros
├── media/                     # Arquivos enviados
├── manage.py                  # Utilitário Django
├── pyproject.toml             # Dependências do projeto
└── README.md                  # Este arquivo
```

## 🔌 Endpoints Principais

### Autenticação
- `POST /auth/register/` - Registrar novo usuário
- `POST /auth/login/` - Login
- `POST /auth/refresh/` - Renovar token JWT

### Mensagens
- `GET /messages/` - Listar mensagens da conversa
- `POST /messages/` - Enviar mensagem
- `POST /messages/{id}/mark-as-read/` - Marcar como lida

### Eventos
- `GET /events/` - Listar eventos
- `POST /events/` - Criar evento
- `PUT /events/{id}/` - Atualizar evento
- `DELETE /events/{id}/` - Deletar evento

### Notificações
- `POST /notifications/register-device/` - Registrar dispositivo
- `GET /notifications/` - Listar notificações

### Crianças
- `GET /children/` - Listar crianças
- `POST /children/` - Adicionar criança

## 🧪 Testes

Execute os testes:
```bash
python manage.py test
```

Ou execute testes específicos:
```bash
python test_integration.py
python test_notifications.py
```

## 📝 Modelos Principais

### User (Django padrão)
Modelo de usuário estendido com perfis

### Conversation
Conversas entre dois ou mais usuários

### Message
Mensagens com suporte a anexos

### Event
Eventos com tipos: custódia, escola, médico, outro

### Child
Informações sobre filhos (CPF, RG, foto, guarda)

### Notification
Sistema de notificações para dispositivos

### DeviceToken
Tokens de dispositivos para push notifications

## 🔐 Autenticação

A API usa JWT (JSON Web Tokens). Para acessar endpoints protegidos, inclua:

```
Authorization: Bearer <seu-token>
```

## 🌐 CORS

Configure os origins permitidos em `settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://seudominio.com",
]
```

## 📚 Documentação

- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- Channels: https://channels.readthedocs.io/
- Firebase Admin: https://firebase.google.com/docs/admin/setup

## 📧 Contato

Para dúvidas ou sugestões, entre em contato com a equipe de desenvolvimento.

## 📄 Licença

Este projeto está licenciado sob a MIT License.
