# Bundled data

## `en_ru_wiktionary.sqlite`

English words with their part of speech and short Russian meanings, used for
offline translations when no AI provider is configured.

- **Source:** the Russian Wiktionary ([ru.wiktionary.org](https://ru.wiktionary.org)),
  extracted by [Wiktextract](https://github.com/tatuylonen/wiktextract) and
  published at [kaikki.org](https://kaikki.org/dictionary/rawdata.html).
- **License:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/),
  © Wiktionary contributors. This file is a derived, abridged work and is
  distributed under the same license; the rest of Kindle Cards is MIT.
- **Changes:** only English entries are kept, form-of glosses are dropped, at
  most four senses per entry and part of speech, glosses shortened to 90
  characters.

Rebuild it from a fresh extract:

```bash
curl -LO https://kaikki.org/dictionary/downloads/ru/ru-extract.jsonl.gz
python packaging/build_dictionary.py ru-extract.jsonl.gz
```
