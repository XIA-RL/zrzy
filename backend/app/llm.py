# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

import httpx

from .models import Plan, PartialPlan

logger = logging.getLogger(__name__)


def _load_supported_regions() -> dict[str, dict]:
    try:
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        return {
            code: {
                "name": cfg.get("region_name", code),
                "province": cfg.get("province", ""),
                "adcode": str(cfg.get("adcode", "")),
                "parent_city": cfg.get("parent_city", ""),
                "province_name": cfg.get("province_name", ""),
            }
            for code, cfg in catalog.get("regions", {}).items()
        }
    except Exception:
        return {"anji": {"name": "\u5b89\u5409\u53bf", "province": "zhejiang", "adcode": "330523"}}


SUPPORTED_REGIONS: dict[str, dict] = _load_supported_regions()


def _build_city_index(regions: dict[str, dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for code, info in regions.items():
        adcode = info.get("adcode", "")
        if len(adcode) >= 4:
            idx.setdefault(adcode[:4], []).append(code)
    return idx


_CITY_INDEX: dict[str, list[str]] = _build_city_index(SUPPORTED_REGIONS)
VALID_YEARS = {2019, 2020, 2021, 2022, 2023}


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def _call_llm(*, base_url: str, api_key: str, model: str, system: str, user: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
    }
    logger.debug("[LM-IN]  system=%s | user=%s", system[:120], user[:200])
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content: str = data["choices"][0]["message"]["content"]
    logger.debug("[LM-OUT] %s", content[:300])
    return content


def _match_region_by_name_and_context(lm_name: str, lm_parent: str, lm_province: str) -> tuple[str, str] | None:
    """用上级地市/省份字段消歧义，避免重名区县错配。"""
    candidates = list(SUPPORTED_REGIONS.items())

    if lm_parent:
        parent_clean = re.sub(r"[\u5e02\u5dde\u76df]$", "", lm_parent.strip())
        by_parent = [
            (code, info)
            for code, info in candidates
            if parent_clean
            and (
                parent_clean == re.sub(r"[\u5e02\u5dde\u76df]$", "", info.get("parent_city", ""))
                or parent_clean in info.get("parent_city", "")
            )
        ]
        if by_parent:
            candidates = by_parent

    if lm_province:
        province_clean = re.sub(r"[\u7701\u5e02\u81ea\u6cbb\u533a\u58ee\u65cf\u56de\u65cf\u7ef4\u543e\u5c14\u7279\u522b\u884c\u653f\u533a]", "", lm_province.strip())
        by_province = [
            (code, info)
            for code, info in candidates
            if province_clean and province_clean in info.get("province_name", "")
        ]
        if by_province:
            candidates = by_province

    # 在上下文候选内优先完全匹配
    for code, info in candidates:
        if info["name"] == lm_name:
            return (code, info["name"])
    for code, info in candidates:
        if lm_name in info["name"] or info["name"] in lm_name:
            return (code, info["name"])

    # 没有上下文命中时再全局完全匹配
    for code, info in SUPPORTED_REGIONS.items():
        if info["name"] == lm_name:
            return (code, info["name"])
    for code, info in SUPPORTED_REGIONS.items():
        if lm_name in info["name"] or info["name"] in lm_name:
            return (code, info["name"])
    return None


def rule_based_plan(text: str) -> Plan:
    models: list[Literal["habitat_quality", "carbon_storage"]] = []
    if re.search(r"\u751f\u5883|\u751f\u5883\u8d28\u91cf|Habitat", text, re.IGNORECASE):
        models.append("habitat_quality")
    if re.search(r"\u78b3|\u78b3\u50a8\u91cf|Carbon", text, re.IGNORECASE):
        models.append("carbon_storage")
    if not models:
        models = ["habitat_quality", "carbon_storage"]
    year = 2023
    m = re.search(r"(19\d{2}|20\d{2})", text)
    if m:
        year = int(m.group(1))
    return Plan(region_code="anji", region_name="\u5b89\u5409\u53bf", year=year, models=models, notes="rule-based")


async def llm_plan(*, text: str, base_url: str, api_key: str, model: str) -> Plan:
    if not api_key:
        return rule_based_plan(text)
    system = (
        "\u4f60\u662f\u4e00\u4e2a GIS \u751f\u6001\u6a21\u578b\u5de5\u4f5c\u6d41\u89c4\u5212\u5668\u3002"
        "\u53ea\u8f93\u51fa JSON\uff0c\u4e0d\u8981\u8f93\u51fa\u591a\u4f59\u6587\u5b57\u3002"
        "\u4ece\u7528\u6237\u6587\u672c\u4e2d\u62bd\u53d6 region_code\u3001region_name\u3001year\uff082019-2023\uff09\u3001models\u3002"
        "models \u53ea\u5141\u8bb8 habitat_quality \u548c carbon_storage\u3002"
    )
    user = (
        f"\u7528\u6237\u8f93\u5165\uff1a{text}\n"
        '{"region_code":"anji","region_name":"\u5b89\u5409\u53bf","year":2023,'
        '"models":["habitat_quality"],"notes":"..."}'
    )
    try:
        content = await _call_llm(base_url=base_url, api_key=api_key, model=model, system=system, user=user)
        return Plan.model_validate(json.loads(_strip_code_fence(content)))
    except Exception:
        return rule_based_plan(text)

async def llm_detect_intent(text: str, *, base_url: str, api_key: str, model: str) -> Literal["invest_analysis", "other"]:
    invest_keywords = r"invest|\u751f\u5883|\u78b3\u50a8\u91cf|\u78b3|\u6a21\u578b|\u5206\u6790|\u8bc4\u4f30|\u751f\u6001|habitat|carbon"
    if not api_key:
        result: Literal["invest_analysis", "other"] = (
            "invest_analysis" if re.search(invest_keywords, text, re.IGNORECASE) else "other"
        )
        logger.debug("[rule] detect_intent -> %s", result)
        return result
    system = (
        "\u5224\u65ad\u7528\u6237\u8f93\u5165\u662f\u5426\u8868\u8fbe\u4e86\u300e\u8fd0\u884c InVEST \u751f\u6001\u6a21\u578b\u5206\u6790\u300f\u7684\u610f\u56fe\u3002"
        "\u53ea\u8f93\u51fa\u4e00\u4e2a\u8bcd\uff1ainvest_analysis \u6216 other\uff0c\u4e0d\u8981\u6709\u4efb\u4f55\u5176\u4ed6\u6587\u5b57\u3002"
    )
    content = await _call_llm(
        base_url=base_url, api_key=api_key, model=model,
        system=system, user=f"\u7528\u6237\u8f93\u5165\uff1a{text}",
    )
    outcome: Literal["invest_analysis", "other"] = (
        "invest_analysis" if "invest_analysis" in content.strip().lower() else "other"
    )
    logger.info("[LM] detect_intent | input=%r | result=%s", text, outcome)
    return outcome


async def llm_extract_region(text: str, *, base_url: str, api_key: str, model: str) -> tuple[str, str] | None:
    if not api_key:
        # ?????????????????????????????
        # ??"??????"?"????"?"???"?????
        parent_match = re.search(
            r"([\u4e00-\u9fa5]{2,6}?(?:\u5e02|\u5dde|\u76df|\u533a|\u5e02\u533a))",
            text,
        )
        lm_parent = parent_match.group(1) if parent_match else ""

        # ?????????????????????????????
        matched_by_full: list[tuple[str, str, str]] = []  # (code, name, adcode)
        for code, info in SUPPORTED_REGIONS.items():
            name = info["name"]
            if name in text:
                matched_by_full.append((code, name, info.get("adcode", "")))

        if matched_by_full:
            # ??????????? adcode ???
            if len(matched_by_full) == 1:
                code, name, _ = matched_by_full[0]
                logger.debug("[rule] extract_region -> %s (%s)", code, name)
                return (code, name)
            # ?????????
            parent_adcode_prefix: str | None = None
            if lm_parent:
                parent_clean = re.sub(r"[\u5e02\u5dde\u76df]$", "", lm_parent)
                for info in SUPPORTED_REGIONS.values():
                    pc = re.sub(r"[\u5e02\u5dde\u76df]$", "", info.get("parent_city", ""))
                    if parent_clean == pc or parent_clean in info.get("parent_city", ""):
                        adcode = info.get("adcode", "")
                        if len(adcode) >= 4:
                            parent_adcode_prefix = adcode[:4]
                            break
            if parent_adcode_prefix:
                for code, name, adcode in matched_by_full:
                    if adcode.startswith(parent_adcode_prefix):
                        logger.debug("[rule] extract_region (disambig) -> %s (%s)", code, name)
                        return (code, name)
            # ???????????
            code, name, _ = matched_by_full[0]
            logger.debug("[rule] extract_region (first) -> %s (%s)", code, name)
            return (code, name)

        # ????????????????????????"??"??"???"?
        for code, info in SUPPORTED_REGIONS.items():
            name = info["name"]
            if text in name:
                logger.debug("[rule] extract_region (partial) -> %s (%s)", code, name)
                return (code, name)

        logger.debug("[rule] extract_region -> None")
        return None

    system = (
        "\u4ece\u7528\u6237\u8f93\u5165\u4e2d\u8bc6\u522b\u76ee\u6807\u884c\u653f\u533a\u53ca\u5176\u4e0a\u4e0b\u6587\uff0c\u7528\u4e8e GIS \u5206\u6790\u3002\n"
        "\u8bf7\u63d0\u53d6\u4e09\u4e2a\u5b57\u6bb5\uff1a\n"
        "  region_name\uff1a\u76ee\u6807\u884c\u653f\u533a\u5b8c\u6574\u540d\u79f0\uff08\u53bf/\u533a/\u5e02\u7ea7\uff09\n"
        "  parent\uff1a\u4e0a\u7ea7\u5730\u7ea7\u5e02\u540d\u79f0\uff08\u5982\u6709\uff09\uff0c\u6ca1\u6709\u5219 null\n"
        "  province\uff1a\u6240\u5728\u7701\u4efd\u540d\u79f0\uff08\u5982\u6709\uff09\uff0c\u6ca1\u6709\u5219 null\n"
        "\u793a\u4f8b1\uff1a\u7528\u6237\u8bf4\u300e\u5357\u4eac\u5e02\u9f13\u697c\u533a\u300f -> "
        "{\"region_name\":\"\u9f13\u697c\u533a\",\"parent\":\"\u5357\u4eac\u5e02\",\"province\":\"\u6c5f\u82cf\u7701\"}\n"
        "\u793a\u4f8b2\uff1a\u7528\u6237\u8bf4\u300e\u5b89\u5409\u300f -> "
        "{\"region_name\":\"\u5b89\u5409\u53bf\",\"parent\":null,\"province\":null}\n"
        "\u8bc6\u522b\u5931\u8d25\u65f6\u8f93\u51fa {\"region_name\":null,\"parent\":null,\"province\":null}\n"
        "\u53ea\u8f93\u51fa JSON\uff0c\u4e0d\u8981\u6709\u4efb\u4f55\u5176\u4ed6\u6587\u5b57\u3002"
    )
    content = await _call_llm(
        base_url=base_url, api_key=api_key, model=model,
        system=system, user=f"\u7528\u6237\u8f93\u5165\uff1a{text}",
    )
    try:
        parsed = json.loads(_strip_code_fence(content))
        lm_name = parsed.get("region_name")
        lm_parent = parsed.get("parent") or ""
        lm_province = parsed.get("province") or ""
        if not lm_name:
            logger.info("[LM] extract_region | input=%r | result=None", text)
            return None
        result = _match_region_by_name_and_context(lm_name, lm_parent, lm_province)
        logger.info("[LM] extract_region | input=%r | lm=(%r,%r) | result=%s", text, lm_name, lm_parent, result)
        return result
    except Exception:
        pass
    logger.info("[LM] extract_region | input=%r | result=None (parse error)", text)
    return None


async def llm_extract_year(text: str, *, base_url: str, api_key: str, model: str) -> int | None:
    if not api_key:
        m = re.search(r"(2019|2020|2021|2022|2023)", text)
        result_year = int(m.group(1)) if m else None
        logger.debug("[rule] extract_year -> %s", result_year)
        return result_year
    system = (
        f"\u4ece\u7528\u6237\u8f93\u5165\u4e2d\u8bc6\u522b\u5e74\u4efd\u3002\u53ea\u63a5\u53d7 {sorted(VALID_YEARS)} \u4e2d\u7684\u5e74\u4efd\u3002"
        "\u53ea\u8f93\u51fa JSON\uff1a{\"year\": 2023} \u6216 {\"year\": null}\uff0c\u4e0d\u8981\u6709\u5176\u4ed6\u6587\u5b57\u3002"
    )
    content = await _call_llm(
        base_url=base_url, api_key=api_key, model=model,
        system=system, user=f"\u7528\u6237\u8f93\u5165\uff1a{text}",
    )
    try:
        parsed = json.loads(_strip_code_fence(content))
        year = parsed.get("year")
        if isinstance(year, int) and year in VALID_YEARS:
            logger.info("[LM] extract_year | input=%r | result=%d", text, year)
            return year
    except Exception:
        pass
    logger.info("[LM] extract_year | input=%r | result=None", text)
    return None


async def llm_extract_models(
    text: str, *, base_url: str, api_key: str, model: str
) -> list[Literal["habitat_quality", "carbon_storage"]] | None:
    if not api_key:
        models: list[Literal["habitat_quality", "carbon_storage"]] = []
        if re.search(r"\u4e24\u4e2a|\u5168\u90e8|\u90fd|all", text, re.IGNORECASE):
            models = ["habitat_quality", "carbon_storage"]
        elif re.search(r"\u751f\u5883|habitat|quality", text, re.IGNORECASE):
            models = ["habitat_quality"]
        elif re.search(r"\u78b3|carbon|storage", text, re.IGNORECASE):
            models = ["carbon_storage"]
        result_models = models if models else None
        logger.debug("[rule] extract_models -> %s", result_models)
        return result_models
    system = (
        "\u4ece\u7528\u6237\u8f93\u5165\u4e2d\u8bc6\u522b\u60f3\u8fd0\u884c\u7684 InVEST \u6a21\u578b\u3002"
        "\u53ef\u9009\u9879\u53ea\u6709\u4e24\u4e2a\uff1ahabitat_quality\uff08\u751f\u5883\u8d28\u91cf\u6a21\u578b\uff09\u3001carbon_storage\uff08\u78b3\u50a8\u91cf\u6a21\u578b\uff09\u3002"
        "\u7528\u6237\u660e\u786e\u8bf4\u4e24\u4e2a\u90fd\u8981\u65f6\u624d\u8fd4\u56de\u4e24\u4e2a\u3002"
        "\u65e0\u6cd5\u786e\u5b9a\u65f6\u8fd4\u56de {\"models\": null}\u3002\u53ea\u8f93\u51fa JSON\u3002"
    )
    content = await _call_llm(
        base_url=base_url, api_key=api_key, model=model,
        system=system, user=f"\u7528\u6237\u8f93\u5165\uff1a{text}",
    )
    try:
        parsed = json.loads(_strip_code_fence(content))
        raw = parsed.get("models")
        if isinstance(raw, list) and raw:
            valid: list[Literal["habitat_quality", "carbon_storage"]] = [
                m for m in raw if m in ("habitat_quality", "carbon_storage")
            ]
            if valid:
                logger.info("[LM] extract_models | input=%r | result=%s", text, valid)
                return valid
    except Exception:
        pass
    logger.info("[LM] extract_models | input=%r | result=None", text)
    return None


async def llm_detect_confirm(text: str, *, base_url: str, api_key: str, model: str) -> bool:
    if not api_key:
        confirmed = bool(re.search(
            r"\u786e\u8ba4|\u662f|\u597d|ok|yes|confirm|\u5f00\u59cb|run", text, re.IGNORECASE
        ))
        logger.debug("[rule] detect_confirm -> %s", confirmed)
        return confirmed
    system = (
        "\u5224\u65ad\u7528\u6237\u8f93\u5165\u662f\u5426\u8868\u793a\u300e\u786e\u8ba4/\u540c\u610f/\u662f\u300f\u3002"
        "\u53ea\u8f93\u51fa JSON\uff1a{\"confirmed\": true} \u6216 {\"confirmed\": false}\u3002"
    )
    content = await _call_llm(
        base_url=base_url, api_key=api_key, model=model,
        system=system, user=f"\u7528\u6237\u8f93\u5165\uff1a{text}",
    )
    try:
        parsed = json.loads(_strip_code_fence(content))
        result_confirm: bool = bool(parsed.get("confirmed", False))
        logger.info("[LM] detect_confirm | input=%r | result=%s", text, result_confirm)
        return result_confirm
    except Exception:
        pass
    return False


async def llm_generate_report(
    result: dict, plan: PartialPlan, *, base_url: str, api_key: str, model: str
) -> str:
    model_labels = []
    if plan.models:
        if "habitat_quality" in plan.models:
            model_labels.append("\u751f\u5883\u8d28\u91cf")
        if "carbon_storage" in plan.models:
            model_labels.append("\u78b3\u50a8\u91cf")

    if not api_key:
        parts = [
            f"**{plan.region_name or plan.region_code} {plan.year}\u5e74\u751f\u6001\u7cfb\u7edf\u670d\u52a1\u8bc4\u4f30\u62a5\u544a**\n",
            f"\u672c\u6b21\u5206\u6790\u8fd0\u884c\u4e86{'?'.join(model_labels)}\u6a21\u578b\u3002",
        ]
        summary = result.get("summary") or result.get("invest", {})
        hq = summary.get("habitat_quality") if isinstance(summary, dict) else None
        cs = summary.get("carbon_storage") if isinstance(summary, dict) else None
        if hq:
            parts.append(
                f"\u751f\u5883\u8d28\u91cf\u5747\u503c\uff1a{hq.get('mean', '\u2014')}\uff0c"
                f"\u8bc4\u7ea7\uff1a{hq.get('level', '\u2014')}\u3002"
            )
        if cs:
            parts.append(f"\u78b3\u50a8\u603b\u91cf\uff1a{cs.get('total_MgC', '\u2014')} MgC\u3002")
        parts.append(
            "\uff08\u5f53\u524d\u4e3a\u89c4\u5219\u5e95\u5e95\u62a5\u544a\uff0c"
            "\u914d\u7f6e LLM_API_KEY \u540e\u53ef\u83b7\u5f97 AI \u751f\u6210\u7684\u6df1\u5ea6\u5206\u6790\u3002\uff09"
        )
        return "\n".join(parts)

    system = (
        "\u4f60\u662f\u4e00\u540d\u4e13\u4e1a\u7684\u751f\u6001\u7cfb\u7edf\u670d\u52a1\u8bc4\u4f30\u5206\u6790\u5e08\u3002"
        "\u6839\u636e\u63d0\u4f9b\u7684 InVEST \u6a21\u578b\u8fd0\u884c\u7ed3\u679c\uff0c"
        "\u7528\u4e2d\u6587\u64b0\u5199\u4e00\u4efd\u7b80\u6d01\u4e13\u4e1a\u7684\u5206\u6790\u62a5\u544a\uff08300\u5b57\u4ee5\u5185\uff09\u3002"
        "\u62a5\u544a\u5e94\u5305\u542b\uff1a\u5206\u6790\u80cc\u666f\u3001\u4e3b\u8981\u7ed3\u8bba\u3001"
        "\u6570\u503c\u89e3\u8bfb\u3001\u7b80\u8981\u5efa\u8bae\u3002\u76f4\u63a5\u8f93\u51fa\u62a5\u544a\u6b63\u6587\uff0c\u4e0d\u9700\u8981\u6807\u9898\u3002"
    )
    user = (
        f"\u5730\u533a\uff1a{plan.region_name or plan.region_code}\uff0c\u5e74\u4efd\uff1a{plan.year}\u5e74\n"
        f"\u8fd0\u884c\u6a21\u578b\uff1a{'?'.join(model_labels)}\n"
        f"\u8fd0\u884c\u7ed3\u679c\uff1a{json.dumps(result, ensure_ascii=False, indent=2)}"
    )
    content = await _call_llm(base_url=base_url, api_key=api_key, model=model, system=system, user=user)
    logger.info("[LM] generate_report | region=%s year=%s", plan.region_code, plan.year)
    return content.strip()
