# Det enda du måste göra (Vapi)

Backend är deployad och accepterar nu **namn** på rätter (menyn är i kod). För att sänka kostnaden och token:

1. Gå till **Vapi** → din Assistant (Gislegrillen) → **Model** → **System prompt**.
2. **Öppna filen `system_prompt_KOMPAKT.md`** i detta repo (Cursor/VS Code).
3. **Kopiera hela innehållet** (Ctrl+A, Ctrl+C).
4. **Klistra in** i Vapi System prompt-fältet (ersätt det som står där).
5. **Spara** Assistant.

Klart. Inget mer. Samma flöde och samma beteende – bara mindre prompt så att varje samtal blir billigare.

**Om något känns fel:** Återställ din gamla prompt (den du hade innan). Backend fungerar med både id och name.
