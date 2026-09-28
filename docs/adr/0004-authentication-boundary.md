# ADR 0004: Isolamento e Fronteira de Autenticação Institucional

## Contexto
O ecossistema DEPED/MDS utiliza ferramentas corporativas da Microsoft (SharePoint, Entra ID / Azure AD, Office 365). Uma integração formal de SSO/SharePoint está sendo construída por outro colaborador. O desenvolvimento e a operação das regras de edital não podem ficar bloqueados aguardando a finalização dessa infraestrutura externa.

## Decisão
Implementamos uma **Fronteira de Autenticação com Padrão Adapter**:
- A aplicação utiliza um Custom User Model (`accounts.User`) com email como identificador primário, preparado para receber claims institucionais (UPN, Azure OID, nome e grupos).
- Um adaptador de autenticação (`apps.accounts.adapters`) define a interface abstrata `AuthenticationAdapter`.
- O adaptador padrão ativo em desenvolvimento é `LocalAuthAdapter`, que usa o mecanismo padrão de senhas e sessões do Django.
- O adaptador futuro `MicrosoftAuthAdapter` implementará a mesma interface sem alterar nenhuma linha dos domínios do edital.
- **Autorização (RBAC) é de responsabilidade estrita da aplicação**, não do provedor de identidade. O provedor apenas atesta "quem é o usuário"; as permissões internas determinam "o que o usuário pode fazer".

## Consequências
- **Positivas:** Desacoplamento total; desenvolvimento e testes funcionam sem credenciais ou rede externa; prontidão plug-and-play para a integração institucional.
- **Negativas:** Exige manter o mapeamento entre grupos do IdP institucional e papéis da aplicação quando o adaptador Microsoft for conectado.
