# Lovable-problem – Förklaring

## Vad loggarna visar

Lovable-appen använder **Lovable Cloud Supabase** (`hiwxknfucwkvpdxwcbxw.supabase.co`), INTE din Gislegrillen-Supabase (`zgllqocecavcgctbduip`).

- **restaurant_memberships** – användare kopplas till restauranger (UUID)
- **orders** – filtreras på `restaurant_id=246c67da-af13-4111-ba7c-c64bf167a551`
- Din backend sparar med `restaurant_id=Gislegrillen_01` (text)

## Två olika databaser

| Källa | Supabase | restaurant_id |
|-------|----------|---------------|
| **Lovable Cloud** | hiwxknfucwkvpdxwcbxw | UUID (246c67da-...) |
| **Din backend** | zgllqocecavcgctbduip | "Gislegrillen_01" |

Edge-funktionen ska hämta från din Supabase, men appen kanske fortfarande läser från Lovable Cloud.

## Inloggning

Du loggar in mot **Lovable Cloud Auth** (hiwxknfucwkvpdxwcbxw). Kontot skapas där – inte i Gislegrillen Supabase.

- Om du inte har konto: **Sign up** i appen (email + lösenord)
- Ditt konto måste finnas i **restaurant_memberships** med rätt restaurant_id

## Vad du ska skriva till Lovable AI

Klistra in:

> "Appen läser fortfarande från Lovable Cloud (hiwxknfucwkvpdxwcbxw) istället för extern Supabase (zgllqocecavcgctbduip). Edge-funktionen fetch-external-orders ska hämta ordrar från extern Supabase – använd den för köksvyn istället för direkt Supabase-query. Våra orders har restaurant_id 'Gislegrillen_01', inte UUID. Hur skapar jag konto och kopplar till Gislegrillen för att se ordrar?"
