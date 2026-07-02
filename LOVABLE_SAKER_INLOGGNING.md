# Sista säkerhetssteget: stäng anonym läsning av ordrar (kräver Lovable-ändring)

## Läget just nu

Allt annat är åtgärdat (2026-07-02):

- `authenticated`-policies som lät vem som helst med konto radera/ändra alla ordrar: **borttagna**.
- Restaurang-scopade policies för inloggade användare (via `restaurant_members`): **skapade och redo**.
- `get_current_restaurant_id()`: anon kan inte längre köra den.

**Kvar:** policyn `anon_select_on_orders` (anonym läsning av `orders`). Den ligger kvar
**medvetet** – Lovable-dashboarden läser ordrar med anon-nyckeln och skulle bli tom
utan den. Att ta bort den utan Lovable-ändring = köket ser inga ordrar.

## Så stängs den helt (5 minuter när du vill)

### Steg 1 – Skapa inloggningsanvändare i Supabase

Kör i Supabase SQL Editor (byt e-post/lösenord):

Dashboard → Authentication → Add user → e-post + lösenord (t.ex. `gislegrillen@dinplattform.se`).

Koppla sedan användaren till restaurangen:

```sql
insert into public.restaurant_members (auth_user_id, restaurant_id)
values (
  (select id from auth.users where email = 'gislegrillen@dinplattform.se'),
  'bd525e53-cfb0-4818-a666-90664cd8414f'
);
```

### Steg 2 – Klistra in detta i Lovable-chatten

> Lägg till inloggning i appen med Supabase Auth (e-post + lösenord). Använd samma
> Supabase-projekt som redan är kopplat. Innan användaren är inloggad ska inga ordrar
> visas – visa en enkel inloggningssida. Efter inloggning: fortsätt läsa från tabellen
> `public.orders` precis som idag (samma kolumner och realtime-prenumeration), men med
> den inloggade sessionens token istället för anon-nyckeln. RLS i databasen filtrerar
> automatiskt så att användaren bara ser sin egen restaurangs ordrar. Logga-ut-knapp i menyn.

### Steg 3 – Verifiera och stäng anon-läsningen

Logga in i Lovable-appen, kontrollera att ordrar syns. Kör sedan i Supabase SQL Editor:

```sql
drop policy if exists anon_select_on_orders on public.orders;
```

Om något strular: policyn kan återskapas direkt (rollback):

```sql
create policy anon_select_on_orders on public.orders for select to anon using (true);
```

### Varför detta är rätt ordning

Nya pizzerior får varsin användare + rad i `restaurant_members` → varje kök ser bara
sina egna ordrar, kundernas telefonnummer är inte längre läsbara anonymt (GDPR), och
ingen kod behöver ändras i backend – policies och medlemstabellen finns redan.
