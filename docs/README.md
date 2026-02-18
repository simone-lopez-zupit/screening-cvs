Prerequisiti

- Python 3.10+ consigliato.
- Variabile ambiente OPENAI_API_KEY impostata con la tua chiave OpenAI.
- Puoi copiare `.env.example` in `.env` e valorizzare `OPENAI_API_KEY, MANATAL_API_KEY, ecc` , poi oppure `source .env` prima di lanciare lo script.

Setup

- (opzionale) python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt



---

## REGOLE

- 🔹 **MANATAL** tutti i CV ricevuti devono andare su manatal per storico
- ✉️ **EMAIL** per tutti i passaggi di stato
- 🚫 **DROP** con email per chi non passa gli step
- 📋 **FORM di VALUTAZIONE** per tutti i colloqui orali
- 📖 **STORICO** di tutto quello che è successo al candidato

---

### ✉️ *APPLICATION sul sito zupit.it*
I CV arrivano per EMAIL

## 🧠 *CHECK RE APPLY*
Se si era già candidato 
- se per stessa posizione e meno di 12 mesi fa --> drop senza email
- altrimenti next

Come controlliamo
- se stessa ascii del CV siamo certi
- se stessa email siamo certi
- se stesso nome e cognome -> `DA VALUTARE`

## 🔍 **SCREENING** chatgpt 
- Un `excel` con
  - dati anagrafici
  - posizione lavorativa attuale
  - progetti personali
  - caratteristiche e spiegazioni:
    - 🇮🇹 ITA: *parla italiano almeno C1*
    - 🤠 AGE: *più giovane di 45 anni*
    - 👶🏼 BOOL: *non ha frequentato boolean o simili*
    - 💀 ACC: *non ha lavorato complessivamente più di 5 anni in Accenture o simile*
    - 🌐 EXP: *ha almeno 3 anni nello sviluppo web*
    - 💼 JOB: *la job position è inerente a full stack developer*
- 🚫 un candidato è `RIFIUTATO` se una di queste è negativa `🇮🇹 🤠 👶🏼 💀`  
- 🤔 un candidato è `DA VALUTARE` se una di queste è negativa `🌐 💼`  
- ☑️ un candidato è `APPROVATO` se tutte sono positive `🇮🇹 🤠 👶🏼 💀 🌐 💼` 
- creazione 6 ZIP dei gruppi di candidati nei 3 stati * se sono nuovi o già esistenti su manatal

## 🏃🏼 **TEST TECNICO** <70% drop

`per i promettenti da CV switch con chiacchierata conoscitiva "così vendiamo Zupit"`

- invio email con link a google form con cui candidato sceglie le tech del test
- appena compilato il form, test dome invia automaticamente il link al test


- 🚫 se drop invio email

## 🍵 **CHIACCHIERATA CONOSCITIVA** con people

- invio email con link reclaim per fissare call con team People


- 🚫 se drop invio email

> da qui in poi tutto manuale tanto sono pochi

## 💻 **COLLOQUIO TECNICO** con TL

- invio email mettendo in copia i tech che faranno il colloquio


- 🚫 se drop invio email

## 🍝 **LIVE CODING** con diverso TL

- invio email mettendo in copia i tech che faranno il colloquio


- 🚫 se drop invio email

## 💸 **PROPOSTA ECONOMICA** con AZ

- invio email con link reclaim di AZ

## 🎉 **ASSUNTO**



- se giovane
- se non giovane
  - deve avere esperienza in Angular