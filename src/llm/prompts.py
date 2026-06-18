# (a) Signal extraction
EXTRACT = """You are a B2B sales-research analyst. From the raw web results below, extract
discrete, factual SIGNALS about the prospect or their company. Do not invent
anything not present in the results. Ignore marketing fluff.
Return at most {max_signals} of the most significant, distinct signals — merge
duplicates and drop trivia.

Prospect: {prospect_name}   Company: {company_name}
Context (optional): {extra_context}
RAW RESULTS (JSON): {research_json}

Return ONLY JSON:
{{"signals":[{{"type":"funding|hiring|product_launch|exec_interview|partnership|expansion|leadership_hire|new_role|challenge|other","description":"<=2 factual sentences","source_url":"...","source_title":"...","published_date":"YYYY-MM-DD or null","funding_meta":{{"round":"...","amount":"..."}},"hook_sentence":"one sentence this could open with"}}]}}
If no real signals exist, return {{"signals":[]}}."""

# (b) Signal scoring
SCORE = """Score each signal for cold-outreach usefulness. Be a skeptical analyst.
Signals (JSON): {signals_json}
Today: {today}   Prospect: {prospect_name} ({role}) @ {company_name}

For EACH signal score 1-10 on: recency (use published_date vs today),
specificity (ties to THIS prospect/role > generic company > industry),
actionability (how naturally it opens a relevant conversation),
confidence (tier-1 press/official > blog/aggregator).
Set is_sensitive=true for layoffs, lawsuits, scandal, financial distress.

Return ONLY JSON: {{"signals":[{{"id":"...","scores":{{"recency":n,"specificity":n,"actionability":n,"confidence":n}},"total_score":avg,"reasoning":"1-2 sentences","is_sensitive":bool}}]}}"""

# (c) Hook selection + justification
HOOK = """Choose the single best outreach angle. Selected signal: {selected_signal_json}
Other available signals: {other_signals_json}
Active flags + rules: {flag_rules}
User instructions (OVERRIDE defaults if present): {user_instructions}
Prospect: {prospect_name} @ {company_name}. Goal: {outreach_goal}

Rules: never use an is_sensitive signal as the hook unless the user explicitly asks;
if funding_round is active, it is the hook; if the chosen signal is stale (>90d),
use it as context, not a literal "I saw you just..." opener.

Return ONLY JSON: {{"hook_text":"angle, not a full email","why_it_matters":"...","why_chosen":"...","why_alternatives_rejected":["sig: reason"]}}"""

# (d) Draft generation
DRAFT = """Write outreach grounded ONLY in the hook and facts below. No invented details,
no fake familiarity, no unsupported claims. Sound human, specific, brief.

Hook: {hook_json}
Prospect: {prospect_name}, {role} @ {company_name}
What we offer: {product_description}   Goal: {outreach_goal}
Framing directive (FOLLOW THIS): {framing_directive}
Tone/length instructions (optional): {user_instructions}

Return ONLY JSON: {{"email":{{"subject":"...","body":"3 short paragraphs, 1 clear CTA"}},"linkedin":{{"body":"<=400 chars, conversational, no subject"}}}}"""

# (e) Edge classifier (LLM-judgment items only)
CLASSIFY = """Decide ONLY whether the research describes multiple different people (ambiguity)
or no usable info. Date/funding/role/account flags are handled in code - ignore them.

Prospect: {prospect_name}  Company: {company_name}
Raw results (JSON): {research_json}

Return ONLY JSON: {{"ambiguous_name":bool,"no_signal":bool,"candidate_identities":[{{"name":"...","company":"...","role":"...","source_url":"..."}}],"evidence":"1-2 sentences"}}"""
