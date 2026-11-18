"""Resolve explicit choice answers without inferring missing or conflicting keys."""
import re


def normalized(text):
    return ' '.join(text.casefold().split())


def resolve_choice_answer(answer, options):
    """Return option IDs and any unlabelled trailing explanation for review."""
    answer = answer.strip()
    exact = [o['id'] for o in options if normalized(o['text']) == normalized(answer)]
    label = re.fullmatch(r'(?:option\s+)?\(?([A-T])(?:\)|[.:])?(?:\s*[-:.)]?\s+(.+))?', answer, re.I)
    if exact:
        if len(exact) != 1 or (label and not label.group(2) and label.group(1).upper() != exact[0]):
            raise ValueError('Answer is ambiguous between an option letter and option text; select the answer manually')
        return exact, ''
    if label:
        found = next((o for o in options if o['id'] == label.group(1).upper()), None)
        if not found:
            raise ValueError('Answer must match an option letter or exact option text')
        detail = (label.group(2) or '').strip()
        if not detail or normalized(detail) == normalized(found['text']):
            return [found['id']], ''
        # A letter plus its exact option text establishes the key. Keep subsequent
        # prose as a tentative explanation and require review rather than dropping it.
        prefix = re.match(re.escape(found['text']) + r'\s+(.+)$', detail, re.I)
        if prefix:
            return [found['id']], prefix.group(1)
        raise ValueError('Answer letter and answer text disagree; select the answer manually')
    if re.search(r'[,|;]', answer):
        resolved = []
        for token in re.split(r'[,|;]', answer):
            ids, tail = resolve_choice_answer(token, options)
            if tail:
                raise ValueError('Multiple answers contain unclear trailing text; review the source')
            resolved.extend(ids)
        return list(dict.fromkeys(resolved)), ''
    raise ValueError('Answer must match an option letter or exact option text')
