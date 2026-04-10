- **Backend:** Python com Flask (roteamento, lógica de negócio e integração com API)
- **Banco de Dados:** SQLite com SQLAlchemy (persistência de dados e relacionamentos)
- **Frontend:** HTML5, CSS3 e JavaScript (requisições assíncronas com AJAX)
- **IA:** Integração com Google Generative AI (Gemini)

---

## 🔄 Fluxo da aplicação

1. Usuário envia um texto pelo frontend
2. O frontend envia a requisição via AJAX para o backend (Flask)
3. O backend processa o texto e envia para a API do Gemini
4. A IA retorna uma análise do conteúdo
5. O backend formata a resposta
6. O resultado é exibido ao usuário em tempo real

---

## 📂 Estrutura do projeto


/FrangoAlert
│
├── FAKEAlert/ # Backend e lógica da aplicação
├── static/ # Arquivos estáticos (CSS, JS)
├── templates/ # HTML (caso use Flask templates)
└── README.md


## 🛠 Tecnologias utilizadas

- Python
- Flask
- SQLite
- SQLAlchemy
- HTML5, CSS3, JavaScript
- Google Generative AI (Gemini)

---

## 🧪 Como rodar o projeto

git clone https://github.com/imthedavi/FrangoAlert
cd FrangoAlert

Instale as dependências:

pip install -r requirements.txt

Execute o servidor:

python app.py

Acesse no navegador:

http://localhost:5000
