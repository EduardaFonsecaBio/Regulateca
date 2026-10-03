# REGULATECA: como colocar o robô para funcionar sozinho

O robô roda no GitHub todo dia às 6h (horário de Brasília), lê as pautas, atas e extratos, e atualiza o painel.

## 1. Criar o repositório (uma vez)
1. Entre no github.com e clique em **New repository** (botão verde, canto superior esquerdo).
2. Nome: `regulateca`. Marque **Public** (o GitHub Pages gratuito exige isso). Clique em **Create repository**.

## 2. Enviar os arquivos
1. Descompacte o `regulateca_robo.zip` no seu computador.
2. Na página do repositório, clique em **uploading an existing file**.
3. Arraste para lá **o conteúdo** da pasta descompactada: `coletor.py`, `regulateca_leitor.py`, `LEIA-ME.md`, a pasta `docs` e a pasta `pdfs`. Clique em **Commit changes**.
4. A pasta `.github` (que começa com ponto) precisa ser criada à mão. Clique em **Add file > Create new file**. No campo do nome, digite exatamente `.github/workflows/atualizar.yml` (as barras criam as pastas). Abra o arquivo `atualizar.yml` do zip no Bloco de Notas, copie todo o texto, cole na página do GitHub e clique em **Commit changes**.

## 3. Liberar o robô para salvar resultados
**Settings > Actions > General > Workflow permissions** e escolha **Read and write permissions**. Clique em **Save**.

## 4. Publicar o painel
**Settings > Pages**. Em *Branch*, escolha `main` e a pasta `/docs`, e clique em **Save**. Em cerca de 1 minuto o endereço do painel aparece no topo da página: `https://SEU-USUARIO.github.io/regulateca/`.

## 5. Rodar a primeira vez
Aba **Actions > Atualizar REGULATECA > Run workflow**. Espere o círculo ficar verde (1 a 3 minutos) e abra o painel. A aba **Relógio Regulatório** mostra a data da última atualização.

Depois disso, o robô roda sozinho todo dia. Você também pode apertar **Run workflow** quando quiser atualizar na hora.

## Se algo não funcionar
- **Ícone vermelho em Actions:** clique nele e me envie o texto da mensagem de erro.
- **"Coleta: ... falhas" no painel:** o robô não conseguiu baixar de um portal. Me envie o texto do arquivo `coleta_status.json` do repositório que eu ajusto.
- **Aviso de que o agendamento foi desativado por inatividade:** em Actions, clique em **Enable workflow**.
- A planilha do Relógio também fica disponível para download em `docs/regulateca_relogio.csv` (abre no Excel).

## Para ajustar palavras e áreas de interesse
Abra `regulateca_leitor.py` no GitHub (ícone do lápis) e edite as listas `KEYWORDS` e `AREAS` no topo do arquivo.
