# Supabase Security Advisor – åtgärdsplan (agent → agent)

Denna fil är en anpassad handlingsplan utifrån Supabase Security Advisor-rapporten. Den tar hänsyn till att **Lovable idag läser ordrar med anon-nyckel** – om du tar bort anon SELECT på `orders` innan Lovable använder inloggning bryter köksvyn.

---

## Snabböversikt – vad Advisor flaggar

| Problem | Tabell(er) | Risk | Vår situation |
|--------|------------|------|----------------|
| RLS Disabled | `restaurants`, `restaurant_members` | Obehörig läsning/skrivning | Backend (Railway) läser `restaurants`, skriver till `orders`. **Använd service_role-nyckel i Railway** så att backend kringgår RLS. Då kan vi säkert aktivera RLS på restaurants/restaurant_members. |
| RLS Policy Always True | `orders` | Alla med anon kan läsa/skriva | **Medvetet** tills Lovable byter till Auth. Lovable behöver anon SELECT för att visa ordrar. **Ta inte bort den** förrän Lovable använder Supabase Auth och ni filtrerar på inloggad användare/restaurang. |
| Sensitive Columns Exposed | `restaurants` | Känsliga fält synliga | Kontrollera om ni har kolumner som `api_key`, `secret` etc. i `restaurants`. Om ja: antingen flytta till `restaurant_secrets` eller skapa vy utan dessa kolumner. Backend behöver bara `id`, `external_id`, `throttle_*`, `deleted_at`. |
| RLS Enabled No Policy | `restaurant_secrets` | All åtkomst blockad | Endast backend (service_role) ska läsa. **Låt RLS vara på utan policy** – då kan bara service_role (som kringgår RLS) läsa. Kontrollera att Railway använder **service_role**-nyckel, inte anon. |

---

## Viktigt innan du ändrar något

1. **Railway (backend):** Sätt **SUPABASE_KEY** till **service_role-nyckeln** (Supabase → Project Settings → API → `service_role` secret), inte anon-nyckeln. Då kringgår backend RLS och kan fortsätta läsa `restaurants` och `restaurant_secrets` och skriva till `orders` även efter att vi aktiverat RLS på andra tabeller.
2. **Lovable:** Använder anon-nyckel och anon SELECT på `orders`. Låt anon SELECT på `orders` vara kvar tills ni implementerat inloggning i Lovable (Supabase Auth) och filtrering per restaurang. Då kan ni ta bort anon-policyn och ersätta med authenticated-baserad policy.

---

## Val: A, B eller C

- **A) Inventera** – Kör bara SQL som listar nuvarande policies och kolumner. Ingen ändring. Rekommenderas först.
- **B) Orders** – Ta bort “always true”-policies på `orders` och skapa restriktiva. **Varning:** Detta bryter Lovable tills ni har Auth. Rekommenderas **inte** nu om ni inte samtidigt byter Lovable till Auth.
- **C) Restaurants + restaurant_members + restaurant_secrets** – Aktivera RLS och skapa säkra policies. Backend måste använda **service_role** (se ovan). Lovable påverkas inte.

**Rekommenderad ordning:** Kör **A** (inventera), sedan **C**. **B** gör ni först när Lovable använder inloggning mot Supabase.

---

## A) Inventera – SQL att köra i Supabase SQL Editor

Kopiera och kör i Supabase → SQL Editor. Spara resultatet så du ser exakt vad som finns idag.

```sql
-- A1: Lista alla policies på public.orders
SELECT pol.polname, pol.polcmd, pg_get_expr(pol.polqual, pol.polrelid) AS using_expr, pg_get_expr(pol.polwithcheck, pol.polrelid) AS with_check
FROM pg_policy pol
JOIN pg_class cls ON cls.oid = pol.polrelid
JOIN pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = 'public' AND cls.relname = 'orders';

-- A2: Lista alla policies på public.restaurants
SELECT pol.polname, pol.polcmd, pg_get_expr(pol.polqual, pol.polrelid) AS using_expr
FROM pg_policy pol
JOIN pg_class cls ON cls.oid = pol.polrelid
JOIN pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = 'public' AND cls.relname = 'restaurants';

-- A3: Lista alla policies på public.restaurant_members
SELECT pol.polname, pol.polcmd, pg_get_expr(pol.polqual, pol.polrelid) AS using_expr
FROM pg_policy pol
JOIN pg_class cls ON cls.oid = pol.polrelid
JOIN pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = 'public' AND cls.relname = 'restaurant_members';

-- A4: Lista alla policies på public.restaurant_secrets
SELECT pol.polname, pol.polcmd, pg_get_expr(pol.polqual, pol.polrelid) AS using_expr
FROM pg_policy pol
JOIN pg_class cls ON cls.oid = pol.polrelid
JOIN pg_namespace ns ON ns.oid = cls.relnamespace
WHERE ns.nspname = 'public' AND cls.relname = 'restaurant_secrets';

-- A5: RLS status per tabell
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND c.relname IN ('orders', 'restaurants', 'restaurant_members', 'restaurant_secrets');

-- A6: Kolumner i public.restaurants (identifiera känsliga)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'restaurants'
ORDER BY ordinal_position;
```

Efter A: granska resultat. Om du ser policy på `orders` med `using_expr = 'true'` är det den anon SELECT som Lovable behöver – **ta inte bort den** förrän ni bytt Lovable till Auth.

---

## C) Fix: restaurants, restaurant_members, restaurant_secrets

Kör detta **efter** att du satt Railway **SUPABASE_KEY** till **service_role** (Project Settings → API → service_role secret). Annars kan backend sluta kunna läsa `restaurants` och `restaurant_secrets`.

**Agent-till-agent (PostgreSQL RLS):** En `CREATE POLICY` får bara ha **en** operation. Använd alltså **inte** `FOR UPDATE, DELETE` i samma rad – det ger syntaxfel. Använd antingen **separata** `CREATE POLICY` per operation (en för UPDATE, en för DELETE) eller `FOR ALL`. I denna plan används alltid separata policies per operation.

**Anpassa kolumnnamn:** Supabase använder ofta `auth_user_id` i `restaurant_members` (kopplat till `auth.uid()`). Om era kolumner heter `auth_user_id` istället för `user_id`, byt alla `user_id` i C2/C3 till `auth_user_id`. Samma för `restaurant_id` i `restaurant_members` – det är vanligtvis uuid (FK till `restaurants.id`). Vi antar: `restaurants` har `id`, `owner_id`; `restaurant_members` har `user_id` (eller `auth_user_id`) och `restaurant_id` (uuid).

### C1: Aktivera RLS

```sql
ALTER TABLE "public"."restaurants" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."restaurant_members" ENABLE ROW LEVEL SECURITY;
-- restaurant_secrets: RLS är redan på (Advisor sa "RLS enabled no policy") – gör inget
```

### C2: Policies för restaurant_members

Om kolumnen heter `auth_user_id` istället för `user_id`, byt i USING/WITH CHECK. **En policy per operation (SELECT, INSERT, UPDATE, DELETE) – kombinera inte FOR UPDATE och FOR DELETE.**

```sql
-- Medlemmar får läsa sina egna rader
CREATE POLICY "member_select_own" ON "public"."restaurant_members"
FOR SELECT TO authenticated
USING ( (SELECT auth.uid()) = user_id );

-- Medlemmar får skapa egen medlemsrad (t.ex. inbjudan)
CREATE POLICY "member_insert_own" ON "public"."restaurant_members"
FOR INSERT TO authenticated
WITH CHECK ( (SELECT auth.uid()) = user_id );

-- Medlemmar får uppdatera egen medlemsrad
CREATE POLICY "member_update_own" ON "public"."restaurant_members"
FOR UPDATE TO authenticated
USING ( (SELECT auth.uid()) = user_id )
WITH CHECK ( (SELECT auth.uid()) = user_id );

-- Medlemmar får radera egen medlemsrad
CREATE POLICY "member_delete_own" ON "public"."restaurant_members"
FOR DELETE TO authenticated
USING ( (SELECT auth.uid()) = user_id );
```

Om `restaurant_members` använder `restaurant_id` som uuid (FK till restaurants.id), behåll som ovan. Om ni har `restaurant_uuid` som kolumnnamn, anpassa vid behov i andra policies som refererar till denna tabell.

### C3: Policies för restaurants

Förutsätter att `restaurants` har `owner_id` (uuid, referens till auth.users). Om ni **inte** har `owner_id`, kan ni istället skapa en mycket restriktiv policy (t.ex. bara tillåta SELECT för authenticated som finns i `restaurant_members` för den restaurangen) och låta endast **service_role** (backend) skriva via API.

```sql
-- Ägare eller medlem i restaurangen får läsa
CREATE POLICY "restaurant_select_owner_or_member" ON "public"."restaurants"
FOR SELECT TO authenticated
USING (
  (owner_id IS NOT NULL AND (SELECT auth.uid()) = owner_id)
  OR id IN (SELECT restaurant_id FROM public.restaurant_members WHERE user_id = (SELECT auth.uid()))
);

-- Endast ägare får skapa (om ni skapar restauranger från klient)
CREATE POLICY "restaurant_insert_owner" ON "public"."restaurants"
FOR INSERT TO authenticated
WITH CHECK ( (SELECT auth.uid()) = owner_id );

-- Ägare eller medlem får uppdatera (begränsa känsliga fält i applikationen)
CREATE POLICY "restaurant_update_owner_or_member" ON "public"."restaurants"
FOR UPDATE TO authenticated
USING (
  (SELECT auth.uid()) = owner_id
  OR id IN (SELECT restaurant_id FROM public.restaurant_members WHERE user_id = (SELECT auth.uid()))
)
WITH CHECK (
  (SELECT auth.uid()) = owner_id
  OR id IN (SELECT restaurant_id FROM public.restaurant_members WHERE user_id = (SELECT auth.uid()))
);

-- Endast ägare får radera
CREATE POLICY "restaurant_delete_owner" ON "public"."restaurants"
FOR DELETE TO authenticated
USING ( owner_id IS NOT NULL AND (SELECT auth.uid()) = owner_id );
```

**Om `restaurants` inte har `owner_id`:** Ta bort eller kommentera bort policies som refererar till `owner_id` och skapa en enklare SELECT-policy som bara tillåter användare som finns i `restaurant_members` för den restaurangen. Backend (service_role) kringgår RLS och påverkas inte.

### C4: restaurant_secrets

Backend läser med **service_role**, som kringgår RLS. **Skapa ingen policy** för anon eller authenticated på `restaurant_secrets` – då förblir endast service_role åtkomst. Om ni senare vill att inloggade användare (t.ex. ägare) ska kunna läsa krypterad config via en säker endpoint, kan ni lägga till en policy då; annars låt det vara som nu.

### C5: Index (prestanda för policies)

```sql
CREATE INDEX IF NOT EXISTS idx_restaurant_members_user_rest
ON public.restaurant_members(user_id, restaurant_id);

CREATE INDEX IF NOT EXISTS idx_restaurants_owner_id
ON public.restaurants(owner_id);
```

(Om kolumnen heter `auth_user_id` i restaurant_members, använd den i indexet.)

---

## B) Orders (gör **inte** förrän Lovable använder Auth)

När ni är redo (Lovable använder Supabase Auth och filtrerar på inloggad användares restaurang):

1. Ta bort anon SELECT-policyn på `orders` (namnet ser du i A1-resultatet).
2. Skapa t.ex.:

```sql
-- Exempel: endast medlemmar i restaurangen får läsa ordrar för den restaurangen
CREATE POLICY "orders_select_restaurant_members" ON "public"."orders"
FOR SELECT TO authenticated
USING (
  restaurant_uuid IN (
    SELECT restaurant_id FROM public.restaurant_members WHERE user_id = (SELECT auth.uid())
  )
);

-- Insert: ofta görs från backend (service_role). Om klienter ska skapa ordrar, begränsa med WITH CHECK.
-- Backend använder service_role så den kringgår RLS.
```

**Validering:** Logga in i Lovable med användare kopplad till restaurang i `restaurant_members` – köksvyn ska visa endast den restaurangens ordrar. Anon ska inte längre få några ordrar.

---

## Känsliga kolumner i restaurants

Om A6 visar kolumner som `api_key`, `secret`, `credentials`:

- **Alternativ 1:** Flytta dem till `restaurant_secrets` (ni har redan den tabellen för krypterad config) och ta bort kolumnerna från `restaurants`.
- **Alternativ 2:** Skapa en vy `restaurants_public` som bara väljer icke-känsliga kolumner (id, name, external_id, address, city, deleted_at, throttle_* etc.) och ge klienter SELECT på vyn istället för på tabellen. Backend använder service_role och kan fortfarande läsa hela tabellen.

---

## Checklista före/efter

- [ ] Railway **SUPABASE_KEY** satt till **service_role** (inte anon) innan du kör C.
- [ ] Kört A (inventera) och sparat resultat.
- [ ] Kört C1–C5 (RLS + policies för restaurants, restaurant_members; inget på restaurant_secrets).
- [ ] Verifierat att backend fortfarande kan: läsa från `restaurants`, läsa från `restaurant_secrets`, skriva till `orders` (ring/testa en order).
- [ ] Lovable visar fortfarande ordrar (anon SELECT på orders oförändrad).
- [ ] B (orders) körs **endast** när Lovable använder Auth och ni har testat i staging.

---

## Kort svar till Supabase (om de frågar)

"Vi har genomfört: 1) Inventering av policies (A). 2) Aktiverat RLS på `restaurants` och `restaurant_members` med ägarskaps-/medlemskap-baserade policies (C). 3) Låtit `restaurant_secrets` vara RLS på utan policy så att endast service_role har åtkomst. 4) **Ändrat inte** anon SELECT på `orders` (USING true) – den krävs av vår köksvy (Lovable) tills vi byter till Auth. 5) Backend använder service_role-nyckel. När Lovable använder inloggning planerar vi att ta bort anon-policyn på orders och ersätta med authenticated policy."
