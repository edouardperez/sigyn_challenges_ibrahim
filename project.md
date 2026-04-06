# PROJET 1 — Analyse de l’endettement d’une entreprise à partir du FEC

## Ta mission

Tu reçois le fichier comptable brut (FEC) d’un salon de coiffure : RD CANNES. Tu dois calculer en Python tous les indicateurs d’endettement de cette entreprise, les comparer au secteur, et nous présenter ta conclusion.

Le FEC est un fichier avec des milliers de lignes d’écritures comptables. C’est à toi de comprendre sa structure, de trouver les bons comptes, et de construire les bons calculs.

-----

## Ce qu’est un FEC

Le Fichier des Écritures Comptables est le fichier brut de la comptabilité d’une entreprise française. Chaque ligne = 1 écriture comptable (une facture, un paiement, un amortissement…).

Les colonnes que tu vas rencontrer :

Colonne
- `JournalCode` = Le type de journal — achats, banque, ventes, opérations diverses, à-nouveau…|
- `CompteNum`   |Le numéro de compte du Plan Comptable Général (PCG). C’est LA clé de tout.  |
- `CompteLib`   |Le nom du compte                                                           
- `CompAuxNum`  |Le sous-compte du tiers (fournisseur ou client spécifique)                  |
- `CompAuxLib`  |Le nom du tiers                                                            
- `EcritureDate`|La date de l’écriture                                                      
- `EcritureLib` |Le descriptif de l’opération                                               
- `Debit`       |Montant au débit                      
- `Credit`      |Montant au crédit                                           

Le Plan Comptable Général français organise les comptes par classe :

```
Classe 1 : Capitaux (ce que l'entreprise possède en fonds propres + ce qu'elle doit à long terme)
Classe 2 : Immobilisations (machines, brevets, véhicules...)
Classe 3 : Stocks
Classe 4 : Tiers (ce que les fournisseurs/clients/État doivent ou sont dus)
Classe 5 : Trésorerie (banque, caisse, placements court terme)
Classe 6 : Charges (les dépenses)
Classe 7 : Produits (les revenus)
```

Pour calculer le solde d’un compte sur un exercice : `somme des débits - somme des crédits`.

C’est tout ce que je te donne. Le reste, tu le découvres en explorant le FEC.

-----

## Les KPIs que tu dois calculer

### 1. Capitaux propres

Les capitaux propres représentent ce que l’entreprise possède “en propre” — l’argent des actionnaires + les bénéfices accumulés.

Ce que tu vas devoir résoudre :

- Quels comptes de classe 1 font partie des capitaux propres ?

- Quelle est la différence entre capitaux propres et capitaux propres APPELÉS ?
- Tous les comptes de classe 1 sont-ils des capitaux propres ? Non. Quels types de comptes tu retrouves en classe 1?

### 2. Endettement financier brut

L’endettement brut = tout ce que l’entreprise doit aux banques et prêteurs.

Ce que tu vas devoir résoudre :

- Où sont les emprunts dans le plan comptable ?
- Quelle est la différence entre une dette à long terme et une dette à court terme (découvert bancaire) —> dans le FEC bien sûr.
- Les deux sont de l’endettement mais elles ne sont PAS dans les mêmes comptes. Trouve-les.
- Attention : les dettes fournisseurs (ce qu’on doit à nos fournisseurs) ne sont PAS de l’endettement financier.

### 3. Trésorerie nette bancaire

La trésorerie nette = le cash réellement disponible, net des découverts.

Ce que tu vas devoir résoudre :

- Quels comptes représentent le cash de l’entreprise ? (il y en a plusieurs types)
- Pourquoi le solde du compte banque seul n’est pas suffisant pour dire “l’entreprise a X€ de cash” ?
- Qu’est-ce qu’un concours bancaire courant et pourquoi ça réduit la trésorerie nette ?
- Si l’entreprise a des placements financiers court terme (VMP), est-ce du cash ?

### 4. Endettement financier net

L’endettement net = endettement brut - la trésorerie disponible.

C’est LE chiffre qui compte. Si une entreprise a 1M€ de dettes mais 800K€ en banque, son endettement net est 200K€.

Ce que tu vas devoir résoudre :

- Construis le calcul en cascade (le “waterfall”) :
  
  ```
  Endettement brut (ce qu'on doit)
  - Cash disponible (ce qu'on a en banque)
  = Endettement net (ce qu'on doit vraiment)
  ```
- Pourquoi le cash pur n’est pas une bonne métrique pour évaluer la solidité financière ?

### 5. Taux d’endettement

Le ratio qui met tout en perspective : combien de dettes pour chaque euro de fonds propres.

Deux versions existent :

**Taux d’endettement brut** = Endettement brut / Capitaux propres 
**Taux d’endettement net** = Endettement net / Capitaux propres

Ce que tu vas devoir résoudre :

- Pourquoi deux versions ? Dans quel cas l’une est plus pertinente que l’autre ?
- Un taux d’endettement de 2x, c’est bien ou mal ? Ça dépend de quoi ?
- Comment la Banque de France calcule-t-elle ces ratios dans leurs fascicules sectorielles ? C’est pas exactement la même manière. Pourquoi ? 

### 6. Charges d’intérêts et coût de la dette

L’endettement a un prix : les intérêts.

Ce que tu vas devoir résoudre :

- Où sont les charges d’intérêts dans le plan comptable ? (classe 6, mais quel sous-compte ?)
- Il existe PLUSIEURS types d’intérêts. Trouve-les. 
Comment pouvons nous comptablement trouver les intérêts dans le PCG ? En général il y a un moyen un peu intuitif je le laisse le trouver (ce mécanisme n’est pas tout le temps vrai mais souvent). 

### 7. Les comptes courants d’associés — la zone grise

C’est LE piège comptable que tu vas découvrir.

Un compte courant d’associé, c’est quand le dirigeant ou un associé prête de l’argent à sa propre entreprise. Comptablement, c’est une DETTE. Économiquement, c’est presque des fonds propres (l’associé ne va pas réclamer son argent du jour au lendemain).

Ce que tu vas devoir résoudre :

- Trouve le compte courant d’associé dans le FEC. Quel est son solde ?
- Faut-il l’inclure dans l’endettement ou dans les quasi-fonds propres ? 
- Si tu le déplaces d’un côté ou de l’autre, comment ça change le taux d’endettement ?
- Argumente ta position. Il n’y a pas de bonne réponse unique — la BdF et les banquiers ne sont pas d’accord entre eux.

### 8. Le waterfall complet

Présente visuellement la cascade complète :

```
Capitaux propres
+ Quasi-fonds propres (si tu décides d'y mettre le compte courant associé)
= Ressources propres

Emprunts long terme
+ Dettes court terme (découvert)
= Endettement brut

Endettement brut
- Disponibilités
- Placements court terme
= Endettement net

Taux d'endettement net = Endettement net / Capitaux propres
```

-----

## Comparaison sectorielle

### Sources

- **SIRET RD CANNES** : 900429929
- **Informations entreprise** : pappers.fr, annuaire-entreprises.data.gouv.fr
- **Benchmarks sectoriels BdF** : https://www.banque-france.fr/fr/publications-et-statistiques/statistiques/fascicules-dindicateurs-sectoriels

### Ce que tu dois faire

1. Identifie le code NAF de RD Cannes (via Pappers ou l’annuaire)
1. Trouve le fascicule BdF correspondant au secteur
1. Repère les ratios d’endettement du secteur (médiane, 1er quartile, 3e quartile)
1. Compare RD Cannes à la médiane sectorielle
1. Conclus : la situation d’endettement est-elle saine, moyenne, ou préoccupante ?

### Questions à te poser

- Est-ce que le ratio de RD Cannes est directement comparable au secteur ? Y a-t-il des biais ?
- Si l’entreprise voulait emprunter 50K€ demain pour rénover le salon, est-ce que sa structure le permet ?
- Quel est le signal le plus inquiétant ET le plus rassurant dans les chiffres ?

-----

## Livrable

Un document (PDF, notebook Jupyter, ou slides) qui contient :

1. **Ton code Python** commenté — chaque bloc explique ce qu’il fait et pourquoi
1. **Les 8 KPIs** avec les montants, les comptes utilisés, et ton raisonnement
1. **Le waterfall visuel** (un graphique ou un schéma)
1. **La comparaison sectorielle** avec les chiffres BdF
1. **Ta conclusion** argumentée sur la situation d’endettement de RD CANNES