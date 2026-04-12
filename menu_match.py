"""
Menymatchning v2.1: exakt/alias → fuzzy (WRatio) med konservativ auto-accept.
Kontrakt: unmatchedItems[].match.type är fuzzy_ambiguous | no_match vid fel.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

# WRatio 0–100 skalas till 0.0–1.0 för trösklar
AUTO_SCORE = 0.92
AMBIGUOUS_SCORE = 0.86
SINGLE_SUGGESTION_AUTO_SCORE = 0.90
MARGIN = 0.05

_INDEX_TTL_SEC = 180
_index_cache: Dict[str, Dict[str, Any]] = {}  # key -> {"index": MenuIndex, "expires_at": float}


def menu_cache_key(rest_id: Optional[str]) -> str:
    return ("menu:%s" % rest_id) if rest_id else "menu"


def invalidate_menu_index_cache(rest_id: Optional[str] = None) -> None:
    if rest_id:
        _index_cache.pop(menu_cache_key(rest_id.strip()), None)
    else:
        _index_cache.clear()


def menu_has_items(menu: dict) -> bool:
    if not menu or not isinstance(menu, dict):
        return False
    for v in menu.values():
        if isinstance(v, list) and len(v) > 0:
            return True
    return False


def normalize(text: str) -> str:
    """
    Gemensam normalisering för meny och input (exakt-nycklar).
    Ingen stopword-borttagning.
    """
    if not text or not isinstance(text, str):
        return ""
    t = text.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    for old in ("-", "_", ".", ",", "/"):
        t = t.replace(old, " ")
    t = re.sub(r"\s+", " ", t).strip()
    # STT: "etthundrafemtio grams" → samma nyckel som "... gram"
    t = re.sub(r"\bgrams\b", "gram", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 90g → 90 gram (samma som i menynamn med gramvikter)
    t = re.sub(r"(\d)\s*g\b", r"\1 gram", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_LEADING_QTY = re.compile(
    r"^(en|ett|två|tre|fyra|fem)\s+",
    re.IGNORECASE,
)


def normalize_input_loose(text: str) -> str:
    """Endast för fuzzy: normalisera + ev. inledande artikel/antal + borttag av generiska suffixord."""
    t = normalize(text)
    t = _LEADING_QTY.sub("", t)
    # Ta bort ord som ofta läggs på i tal men inte ingår i menynamn.
    # Vi tar bara bort om det finns fler än ett token för att undvika att "förstöra" korta namn.
    tokens = [p for p in t.split(" ") if p]
    if len(tokens) > 1:
        drop = {"pizza", "pizzan", "pizzor", "pizzorna"}
        tokens = [p for p in tokens if p not in drop]
        t = " ".join(tokens)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class MenuIndex:
    rest_id: str
    lookup: Dict[str, int] = field(default_factory=dict)
    key_kind: Dict[str, str] = field(default_factory=dict)
    colliding_keys: Set[str] = field(default_factory=set)
    canonical_by_id: Dict[int, str] = field(default_factory=dict)
    fuzzy_candidates: List[Tuple[int, str]] = field(default_factory=list)

    def match_one(self, input_name: str, rest_id_log: str) -> Dict[str, Any]:
        """
        Returnerar dict med type: exact | alias | fuzzy_auto | fuzzy_ambiguous | no_match
        och fält för respektive typ.
        """
        n = normalize(input_name)
        if n and n in self.lookup:
            iid = self.lookup[n]
            kind = self.key_kind.get(n, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {
                "type": out_type,
                "itemId": iid,
                "canonicalName": canon,
            }
        ns = n.replace(" ", "") if n else ""
        if ns and ns in self.lookup:
            iid = self.lookup[ns]
            kind = self.key_kind.get(ns, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {
                "type": out_type,
                "itemId": iid,
                "canonicalName": canon,
            }

        nl = normalize_input_loose(input_name)
        # Tal/STT: "en etthundrafemtio grams hamburgare" → samma alias som utan inledande artikel
        if nl and nl != n and nl in self.lookup:
            iid = self.lookup[nl]
            kind = self.key_kind.get(nl, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {
                "type": out_type,
                "itemId": iid,
                "canonicalName": canon,
            }
        nls = nl.replace(" ", "") if nl else ""
        if nls and nls != ns and nls in self.lookup:
            iid = self.lookup[nls]
            kind = self.key_kind.get(nls, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {
                "type": out_type,
                "itemId": iid,
                "canonicalName": canon,
            }

        if not nl:
            print('MENU_MATCH rest_id=%s type=no_match input=%r (tom efter loose)' % (rest_id_log, input_name[:120]))
            return {"type": "no_match"}

        # Efter "loose" normalisering kan vi ibland landa på en exakt/alias-nyckel.
        # Ex: "Småland Pizza" -> "smaland" som finns i lookup.
        if nl in self.lookup:
            iid = self.lookup[nl]
            kind = self.key_kind.get(nl, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s (via loose exact)'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {"type": out_type, "itemId": iid, "canonicalName": canon}
        nls = nl.replace(" ", "")
        if nls and nls in self.lookup:
            iid = self.lookup[nls]
            kind = self.key_kind.get(nls, "canonical")
            out_type = "alias" if kind == "alias" else "exact"
            canon = self.canonical_by_id[iid]
            print(
                'MENU_MATCH rest_id=%s type=%s input=%r -> %r id=%s (via loose exact nospace)'
                % (rest_id_log, out_type, input_name[:120], canon[:80], iid)
            )
            return {"type": out_type, "itemId": iid, "canonicalName": canon}

        scored: List[Tuple[float, int]] = []
        for item_id, cand_norm in self.fuzzy_candidates:
            if not cand_norm:
                continue
            raw = fuzz.WRatio(nl, cand_norm)
            scored.append((raw / 100.0, item_id))

        scored.sort(key=lambda x: (-x[0], x[1]))
        # Behåll bästa score per itemId
        best_by_id: Dict[int, float] = {}
        for sc, iid in scored:
            if iid not in best_by_id:
                best_by_id[iid] = sc
        ranked = sorted(best_by_id.items(), key=lambda x: (-x[1], x[0]))
        if not ranked:
            print('MENU_MATCH rest_id=%s type=no_match input=%r top3=[]' % (rest_id_log, input_name[:120]))
            return {"type": "no_match"}

        best_id, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        second_id = ranked[1][0] if len(ranked) > 1 else None

        top3_log = []
        for iid, sc in ranked[:3]:
            top3_log.append((self.canonical_by_id.get(iid, "?"), round(sc, 4)))

        if best_score >= AUTO_SCORE and (best_score - second_score) >= MARGIN:
            canon = self.canonical_by_id[best_id]
            print(
                'MENU_MATCH rest_id=%s type=fuzzy_auto input=%r -> %r id=%s score=%.3f second=%.3f top3=%s'
                % (
                    rest_id_log,
                    input_name[:120],
                    canon[:80],
                    best_id,
                    best_score,
                    second_score,
                    top3_log,
                )
            )
            return {
                "type": "fuzzy_auto",
                "itemId": best_id,
                "canonicalName": canon,
                "score": best_score,
                "secondScore": second_score,
            }

        if best_score >= AMBIGUOUS_SCORE:
            ids_sug: List[int] = [best_id]
            scores_out: List[float] = [best_score]
            if second_id is not None and second_score >= AMBIGUOUS_SCORE and len(ids_sug) < 2:
                ids_sug.append(second_id)
                scores_out.append(second_score)
            names = [self.canonical_by_id[i] for i in ids_sug]
            print(
                'MENU_MATCH rest_id=%s type=fuzzy_ambiguous input=%r suggestions=%r scores=%s top3=%s'
                % (rest_id_log, input_name[:120], names, [round(s, 4) for s in scores_out], top3_log)
            )
            return {
                "type": "fuzzy_ambiguous",
                "suggestions": names[:2],
                "scores": [round(s, 4) for s in scores_out][:2],
            }

        print(
            'MENU_MATCH rest_id=%s type=no_match input=%r top3=%s'
            % (rest_id_log, input_name[:120], top3_log)
        )
        return {"type": "no_match"}


def build_menu_index(menu: dict, rest_id: str) -> MenuIndex:
    lookup: Dict[str, int] = {}
    key_kind: Dict[str, str] = {}
    colliding: Set[str] = set()
    canonical_by_id: Dict[int, str] = {}
    fuzzy_candidates: List[Tuple[int, str]] = []

    def collision_remove(key: str) -> None:
        colliding.add(key)
        lookup.pop(key, None)
        key_kind.pop(key, None)

    def try_add_key(key: str, item_id: int, kind: str) -> None:
        if not key or key in colliding:
            return
        ex = lookup.get(key)
        if ex is not None and ex != item_id:
            print(
                "MENU_KEY_COLLISION rest_id=%s key=%r ids=[%s,%s]"
                % (rest_id, key[:80], ex, item_id)
            )
            collision_remove(key)
            return
        lookup[key] = item_id
        key_kind[key] = kind

    for items in menu.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_name = (item.get("name") or "").strip()
            if not raw_name:
                continue
            try:
                item_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            canonical_by_id[item_id] = raw_name
            cn = normalize(raw_name)
            try_add_key(cn, item_id, "canonical")
            try_add_key(cn.replace(" ", ""), item_id, "canonical")
            aliases = item.get("aliases")
            if isinstance(aliases, list):
                for a in aliases:
                    if isinstance(a, str) and a.strip():
                        an = normalize(a.strip())
                        try_add_key(an, item_id, "alias")
                        try_add_key(an.replace(" ", ""), item_id, "alias")
            fuzzy_candidates.append((item_id, cn))

    return MenuIndex(
        rest_id=rest_id,
        lookup=lookup,
        key_kind=key_kind,
        colliding_keys=colliding,
        canonical_by_id=canonical_by_id,
        fuzzy_candidates=fuzzy_candidates,
    )


def get_or_build_menu_index(rest_id: Optional[str], menu: dict) -> Optional[MenuIndex]:
    """None om menyn saknar artiklar. Cachas per rest_id med TTL."""
    if not menu_has_items(menu):
        return None
    key = menu_cache_key(rest_id)
    now = time.time()
    ent = _index_cache.get(key)
    if ent and now < ent["expires_at"]:
        return ent["index"]
    rid = (rest_id or "").strip() or "Gislegrillen_01"
    idx = build_menu_index(menu, rid)
    _index_cache[key] = {"index": idx, "expires_at": now + _INDEX_TTL_SEC}
    return idx


def resolve_order_items(
    items_data: List[dict],
    index: MenuIndex,
    rest_id_log: str,
) -> Tuple[bool, List[dict], List[dict]]:
    """
    Matcha alla rader. Returnerar (all_ok, resolved_rows, unmatched_for_api).
    unmatched_for_api följer Vapi-kontraktet (index 0-baserat).
    """
    resolved: List[dict] = []
    unmatched: List[dict] = []

    for i, d in enumerate(items_data):
        if not isinstance(d, dict):
            unmatched.append(
                {
                    "index": i,
                    "input": "",
                    "match": {
                        "type": "no_match",
                        "suggestions": [],
                        "scores": [],
                    },
                }
            )
            continue
        raw_id = d.get("id")
        by_id: Optional[int] = None
        if raw_id is not None:
            try:
                cand = int(raw_id)
                if cand in index.canonical_by_id:
                    by_id = cand
            except (TypeError, ValueError):
                pass

        if by_id is not None:
            name = index.canonical_by_id[by_id]
            print(
                'MENU_MATCH rest_id=%s type=exact input=%r -> %r id=%s (via id)'
                % (rest_id_log, (d.get("name") or "")[:80], name[:80], by_id)
            )
            row = dict(d)
            row["id"] = by_id
            row["name"] = name
            resolved.append(row)
            continue

        name_in = (d.get("name") or "").strip()
        if not name_in:
            unmatched.append(
                {
                    "index": i,
                    "input": "",
                    "match": {
                        "type": "no_match",
                        "suggestions": [],
                        "scores": [],
                    },
                }
            )
            continue

        m = index.match_one(name_in, rest_id_log)
        mt = m.get("type")
        if mt in ("exact", "alias", "fuzzy_auto"):
            iid = m["itemId"]
            canon = index.canonical_by_id[iid]
            row = dict(d)
            row["id"] = iid
            row["name"] = canon
            resolved.append(row)
        elif mt == "fuzzy_ambiguous":
            # Om vi bara har en kandidat och den är stark nog, auto-acceptera istället för att stoppa ordern.
            sug = m.get("suggestions") or []
            scores = m.get("scores") or []
            if len(sug) == 1 and scores:
                try:
                    sc0 = float(scores[0])
                except (TypeError, ValueError):
                    sc0 = 0.0
                if sc0 >= SINGLE_SUGGESTION_AUTO_SCORE:
                    target_name = sug[0]
                    target_id = None
                    for _id, _canon in index.canonical_by_id.items():
                        if _canon == target_name:
                            target_id = _id
                            break
                    if target_id is not None:
                        row = dict(d)
                        row["id"] = target_id
                        row["name"] = target_name
                        resolved.append(row)
                        continue
            unmatched.append(
                {
                    "index": i,
                    "input": name_in,
                    "match": {
                        "type": "fuzzy_ambiguous",
                        "suggestions": sug,
                        "scores": scores,
                    },
                }
            )
        else:
            unmatched.append(
                {
                    "index": i,
                    "input": name_in,
                    "match": {
                        "type": "no_match",
                        "suggestions": [],
                        "scores": [],
                    },
                }
            )

    ok = len(unmatched) == 0
    return ok, resolved, unmatched


def place_order_fail_json(error: str, unmatched: List[dict]) -> str:
    import json

    return json.dumps(
        {
            "success": False,
            "error": error,
            "unmatchedItems": unmatched,
        },
        ensure_ascii=False,
    )
