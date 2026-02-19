# Varför ingen deployment på Railway – och vad du gör

Du pushade till **GitHub-repot:** `william6888/swedenvoice-platform` (branch `main`).

Railway bygger bara när den är **kopplad till det repot (och rätt branch)**.

---

## 1. Kolla vad Railway är kopplad till

1. Gå till **railway.app** → logga in → öppna **projektet** som hostar Gislegrillen/SwedenVoice.
2. Öppna **din app/service** (den som kör backend).
3. Gå till **Settings** (eller **Source** / **Connect Repo**).
4. Se vilket **GitHub-repo** och vilken **branch** som står:
   - Står det **Gislegrillen_ny** eller något annat → Railway lyssnar inte på `swedenvoice-platform`.
   - Står det **swedenvoice-platform** och **main** → då borde push ha triggat deploy (gå till steg 2).

---

## 2. Om Railway redan är kopplad till swedenvoice-platform

- **Redeploy manuellt:** Öppna appen på Railway → fliken **Deployments** → klicka **Redeploy** på senaste deployment, eller **Deploy** / **Trigger Deploy** om det finns.
- Kolla **Build/Deploy-loggen** – om det står "No new commits" eller att den bygger från annan branch, byt till branch **main** under Source-inställningarna.

---

## 3. Om Railway är kopplad till ett annat repo (t.ex. Gislegrillen_ny)

Välj ett av:

**A) Byta till swedenvoice-platform (rekommenderat)**  
- I Railway: **Settings** → **Source** / **Repository** → **Change** eller **Disconnect** → **Connect** till repot **swedenvoice-platform**, branch **main**.  
- Spara. Railway gör då en ny deploy från `swedenvoice-platform` main.

**B) Fortsätta använda det andra repot**  
- Pusha samma kod till det repot:  
  `git remote add other https://github.com/william6888/Gislegrillen_ny.git`  
  `git push other main`  
  (Om du vill att Railway ska bygga från Gislegrillen_ny istället.)

---

## 4. Snabbkontroll

Efter att Railway byggt och deployat: kör lokalt  
`python3 test_order_railway.py`  
– om det redan ger 200 och order skapas använder Railway redan en tidigare deploy; då behöver du bara koppla om till **swedenvoice-platform** (steg 3A) så att framtida push dit triggar deploy.
