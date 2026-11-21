"""Web-search API adapters. No network request is made on import."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def post(url, headers, payload):
    req = Request(url, data=json.dumps(payload).encode(),
                  headers={'Content-Type': 'application/json', **headers}, method='POST')
    try:
        with urlopen(req, timeout=300) as response:
            return json.load(response)
    except HTTPError as exc:
        # Include only simple provider error codes; never echo bodies or request URLs.
        codes = []
        try:
            error = json.loads(exc.read()).get('error', {})
            if isinstance(error, dict):
                for field in ('type', 'code', 'status'):
                    value = str(error.get(field, ''))
                    if value and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value):
                        codes.append(f'{field}={value}')
        except (ValueError, AttributeError):
            pass
        finally:
            exc.close()
        detail = '; ' + ', '.join(codes) if codes else ''
        raise RuntimeError(f'Provider HTTP {exc.code}{detail}; check model access, billing, quotas, and web-search support.') from None
    except URLError:
        raise RuntimeError('Provider connection failed. Resume this batch to retry unsaved slots.') from None


def ask(provider, model, prompt, key):
    if provider == 'OpenAI':
        raw = post('https://api.openai.com/v1/responses', {'Authorization': f'Bearer {key}'},
                   {'model': model, 'input': prompt, 'tools': [{'type': 'web_search'}]})
        if raw.get('status') != 'completed':
            raise ValueError('OpenAI response did not complete.')
        parts = [p for item in raw.get('output', []) if item.get('type') == 'message'
                 for p in item.get('content', [])]
        if any(p.get('type') == 'refusal' for p in parts):
            raise ValueError('OpenAI refused the request; response excluded from sentiment input.')
        text = '\n'.join(p.get('text', '') for p in parts if p.get('type') == 'output_text')
        links = [a['url'] for p in parts for a in p.get('annotations', [])
                 if a.get('type') == 'url_citation' and a.get('url')]
        return result(text, links, raw.get('model', ''), raw,
                      sum(i.get('type') == 'web_search_call' for i in raw.get('output', [])))
    if provider == 'Claude':
        messages, raws, content = [{'role': 'user', 'content': prompt}], [], []
        for _ in range(4):
            raw = post('https://api.anthropic.com/v1/messages',
                       {'x-api-key': key, 'anthropic-version': '2023-06-01'},
                       {'model': model, 'max_tokens': 16000, 'messages': messages,
                        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 5}]})
            raws.append(raw); content.extend(raw.get('content', []))
            if raw.get('stop_reason') != 'pause_turn':
                break
            messages.append({'role': 'assistant', 'content': raw['content']})
        if raw.get('stop_reason') != 'end_turn':
            raise ValueError('Claude response did not complete normally.')
        errors = [x for b in content if b.get('type') == 'web_search_tool_result'
                  for x in (b.get('content') if isinstance(b.get('content'), list) else [b.get('content', {})])
                  if isinstance(x, dict) and x.get('type') == 'web_search_tool_result_error']
        if errors:
            raise ValueError('Claude reported a web-search tool error.')
        text = ''.join(b.get('text', '') for b in content if b.get('type') == 'text')
        links = [c['url'] for b in content for c in b.get('citations', []) or [] if c.get('url')]
        return result(text, links, raw.get('model', ''), raws,
                      sum(b.get('type') == 'server_tool_use' and b.get('name') == 'web_search' for b in content))
    if provider == 'Gemini':
        model_path = quote(model.removeprefix('models/'), safe='')
        raw = post(f'https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent',
                   {'x-goog-api-key': key},
                   {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                    'tools': [{'google_search': {}}]})
        candidate = (raw.get('candidates') or [{}])[0]
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Gemini response blocked or incomplete.')
        text = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
        grounding = candidate.get('groundingMetadata', {})
        links = [c['web']['uri'] for c in grounding.get('groundingChunks', []) if c.get('web', {}).get('uri')]
        return result(text, links, raw.get('modelVersion', ''), raw, len(grounding.get('webSearchQueries', [])))
    raise ValueError(f'Unknown provider: {provider}')


def result(text, links, model, raw, searches):
    if not text.strip():
        raise ValueError('Provider returned an empty answer.')
    return {'response_text': text, 'citation_urls': json.dumps(list(dict.fromkeys(links)), ensure_ascii=False),
            'model_returned': model, 'raw_response': raw, 'search_count': searches}
