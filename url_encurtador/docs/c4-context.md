# C4 - Nível 1: Diagrama de Contexto

```mermaid
C4Context
    title Encurtador de URL - Diagrama de Contexto

    Person(cliente, "Cliente", "Acessa URLs encurtadas pelo navegador ou outro cliente HTTP")
    Person(desenvolvedor, "Desenvolvedor/Sistema integrador", "Cria URLs encurtadas via API")

    System(encurtador, "Encurtador de URL", "Gera códigos curtos e redireciona para a URL original")

    Rel(desenvolvedor, encurtador, "Cria URL curta", "HTTPS POST /urls")
    Rel(cliente, encurtador, "Acessa URL curta", "HTTPS GET /{code}")
```

## Atores

- **Cliente**: qualquer pessoa ou sistema que recebe um link curto e o acessa para ser redirecionado
  à URL original.
- **Desenvolvedor/Sistema integrador**: quem chama `POST /urls` para gerar um novo código curto
  (ex: um backend de outra aplicação, um time de marketing, etc.).

## Sistema

- **Encurtador de URL**: sistema único, todo on-premises/local (sem dependências de nuvem),
  responsável por gerar códigos curtos, persistir o mapeamento `code -> URL original` e redirecionar
  requisições de leitura.
