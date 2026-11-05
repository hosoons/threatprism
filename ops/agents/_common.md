Common contract for every ThreatPrism collector agent
- Read the rule files given in your task (collection.md, scoring.md) before you start. Today's date (KST) and the output path are given in your task.
- Use WebSearch/WebFetch only. Do not publish, push, email or post anything; you only write ONE JSON file (an array of candidate objects, UTF-8, Korean left unescaped) to the output path with a short Python script.
- Search in English and Korean as relevant; check tier-1 sources first, then tier-2. Open every article you keep.
- Skip anything already listed in the "recent titles/URLs" file given in your task unless it is a genuine follow-up (then set followUpOf).
- Quality over quantity: return at most the number of candidates stated for your scope, best first. Fill scoreFactors honestly from the article facts.
- Final reply (keep it to one line to save tokens): "done N candidates" or "failed: reason".
