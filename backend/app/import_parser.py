"""Conservative extraction: explicit answer evidence only, ambiguous layouts go to AI/review."""
import re
from pydantic import ValidationError
from .document_import import START, OPTION, ANSWER, split_inline_question_parts
from .import_schema import question_adapter, preview_row

TYPE = re.compile(r'^(?:type|question type)\s*:\s*(.+)$',re.I)
CHECK = re.compile(r'[\u2713\u2714\u2611\u2705]')
BANNER = re.compile(r'^(?:.+\|\s*)?(?:question|q|mcq)\s*(\d+)\s*/\s*\d+\s*$',re.I)
KEY_ENTRY = re.compile(r'^(?:(?:Q|Question)\s*)?(\d+)[.):\s-]+(?:Answer\s*:\s*)?(.+)$',re.I)
KEY_HEADING = re.compile(r'^(?:answers?|answer key|solutions?)(?:\s*[:\u2013\u2014-]?\s*(?:\(?\s*(?:questions?\s*)?\d+\s*[-\u2013\u2014]\s*\d+\s*\)?))?\s*:?$',re.I)


def positioned_lines(section):
    """Pair standalone option badges with nearby text, without guessing answers.

    Original blocks remain intact for AI. Only unambiguous one-to-one spatial
    matches become options; uncertain layouts retain the ordinary text fallback.
    """
    blocks=[b for b in section.get('blocks',[]) if b.get('text','').strip() and 'x' in b]
    labels=[b for b in blocks if re.fullmatch(r'[A-T]',b['text'].strip())]
    if len(labels)<2 or len({b['text'].strip() for b in labels})!=len(labels):return None
    pairs=[];used=set()
    for label in labels:
        center=label['y']+label['height']/2
        candidates=[b for b in blocks if b not in labels and b['shape_id'] not in used
                    and b.get('parent')==label.get('parent')
                    and b['x']>=label['x']+label['width']*.8
                    and abs(b['y']+b['height']/2-center)<=max(b['height'],label['height'])*.6
                    and not ANSWER.match(b['text'].strip())]
        candidates.sort(key=lambda b:b['x']-(label['x']+label['width']))
        if not candidates:return None
        value=candidates[0]
        # Two equally close boxes do not establish a safe relationship.
        if len(candidates)>1 and candidates[1]['x']==value['x']:return None
        used.add(value['shape_id']);used.add(label['shape_id']);pairs.append((label,value))
    first_option=min(min(label['y'],value['y']) for label,value in pairs)
    before=[];after=[];answers=[];explanations=[];context=[]
    for block in sorted(blocks,key=lambda b:(b['y'],b['x'])):
        if block['shape_id'] in used:continue
        text=block['text'].strip()
        if block.get('is_footer') or re.fullmatch(r'\d+\s*/\s*\d+',text) or re.match(r'^MCQ\s+\d+\s*:',text,re.I):
            context.append({'shape_id':block['shape_id'],'text':text,'reason':'slide heading or repeated footer'});continue
        if ANSWER.match(text):answers.append(text)
        elif re.match(r'^(?:key idea|explanation)\s*:',text,re.I):explanations.append('Explanation: '+text.split(':',1)[1].strip())
        elif block['y']<first_option:before.append(text)
        else:after.append(text)
    if not before:return None
    section['parser_context']=context
    # Unknown residual content is retained and reported, never used as an answer.
    if after:
        section.setdefault('warnings',[]).append('Unassociated text boxes: '+' | '.join(after)[:500])
    else:section['parser_layout_resolved']=True
    lines=[*before,*[label['text'].strip()+') '+value['text'].strip() for label,value in sorted(pairs,key=lambda pair:pair[0]['text'])],*answers,*explanations]
    if section.get('notes'):lines.extend(section['notes'].splitlines())
    return lines


def parse_question(lines, source):
    title=[];options=[];answers=[];explanation=[];kind=None;mode='title';marks='1';evidence=[];model_answer=[]
    for line in lines:
        for text in split_inline_question_parts(line):
            original_text=text
            leading_check=bool(CHECK.match(text))
            if leading_check:text=CHECK.sub('',text).strip()
            answer=ANSWER.match(text);option=OPTION.match(text);type_match=TYPE.match(text)
            if type_match:
                kind=type_match.group(1).lower().replace('/','_').replace(' ','_').replace('-','_')
                kind={'true/false':'true_false','true_false':'true_false','shortanswer':'short_answer','multiple_choice':'mcq'}.get(kind,kind)
            elif re.match(r'^(?:accepted answers?|model answer)\s*:',text,re.I):
                label,value=text.split(':',1)
                kind=kind or 'short_answer'
                if label.lower().startswith('model'):
                    model_answer.append(value.strip());mode='model_answer'
                else:
                    answers.append(value.strip());mode='answer'
                evidence.append(original_text)
            elif answer:
                if answer.group(1).strip(): answers.append(answer.group(1).strip());evidence.append(text)
                mode='answer'
            elif re.match(r'^explanation\s*:',text,re.I): explanation.append(text.split(':',1)[1].strip());mode='explanation'
            elif re.match(r'^marks\s*:',text,re.I):marks=text.split(':',1)[1].strip()
            elif option and mode != 'explanation':
                label=option.group(1).upper();value=option.group(2).strip()
                marked=leading_check or bool(CHECK.search(value));value=CHECK.sub('',value).strip()
                if any(o['id']==label for o in options): raise ValueError('Duplicate option labels; question boundaries require review')
                options.append({'id':label,'text':value});mode='option'
                if marked: answers.append(label);evidence.append(original_text)
            elif mode=='answer':answers.append(text);evidence.append(text)
            elif mode=='explanation':explanation.append(text)
            elif mode=='model_answer':model_answer.append(text);evidence.append(original_text)
            elif mode=='option': options[-1]['text']+=' '+text
            else:title.append(text)
    question=' '.join(title).strip()
    if not question: raise ValueError('Question text could not be identified')
    # Explicit response types can be prefix labels without requiring a Type: field.
    prefix=re.match(r'^(True\s*[/\u2013-]\s*False|Short Answer|Survey|Poll)\s*[:.]\s*(.*)$',question,re.I)
    if prefix:
        kind=prefix.group(1).lower().replace(' ','').replace('/','_')
        kind={'true_false':'true_false','shortanswer':'short_answer'}.get(kind,kind);question=prefix.group(2)
    if not kind and options and [o['text'].casefold() for o in options]==['true','false']: kind='true_false'
    if not kind:kind='mcq' if options else 'short_answer'
    raw={'type':kind,'question':question,'source':source,'explanation':' '.join(explanation),'marks':marks,'answer_origin':'source' if answers or any(model_answer) else 'missing'}
    raw['source']['answer_evidence']='\n'.join(evidence)
    if kind in {'mcq','multiple_select','quiz','true_false','ranking','poll','survey'}:
        if kind=='true_false' and not options: options=[{'id':'True','text':'True'},{'id':'False','text':'False'}]
        if options: raw['options']=options
        if kind in {'mcq','multiple_select','quiz','true_false'}:
            resolved=[]
            for answer in answers:
                exact=next((o for o in options if o['text'].casefold()==answer.casefold()),None)
                if exact:resolved.append(exact['id']);continue
                for token in re.split(r'[,|;]',answer):
                    token=token.strip()
                    match=re.fullmatch(r'(?:option\s+)?\(?([A-T])(?:\)|[.:])?(?:\s*[-:.)]?\s+(.+))?',token,re.I)
                    found=next((o for o in options if o['id']==(match.group(1).upper() if match else token)),None)
                    if not found: raise ValueError('Answer must match an option letter or exact option text')
                    if match and match.group(2) and match.group(2).strip()!=found['text']:raise ValueError('Answer letter and answer text disagree')
                    resolved.append(found['id'])
            resolved=list(dict.fromkeys(resolved))
            if kind=='mcq' and len(resolved)>1:raw['type']='multiple_select'
            raw['correct_answers']=resolved
    elif kind=='short_answer':
        raw['accepted_answers']=[x.strip() for a in answers for x in a.split('|') if x.strip()]
        raw['model_answer']=' '.join(model_answer).strip()
        raw['requires_review']=not bool(raw['accepted_answers'] or raw['model_answer'])
    return question_adapter.validate_python(raw)


def parse_structure(sections, filename, format):
    blocks=[];current=[];locations=[];current_id=None;keys={};errors=[]
    def finish():
        nonlocal current,locations,current_id
        if current:blocks.append((current_id,current,locations))
        current=[];locations=[];current_id=None
    for section in sections:
        spatial=positioned_lines(section) if format=='pptx' else None
        lines=[x.strip() for x in (spatial if spatial is not None else section['text'].replace('\v','\n').splitlines()) if x.strip()]
        if spatial is None and format=='pptx' and not any(OPTION.match(x) or ANSWER.match(x) or START.match(x) or '?' in x for x in lines):
            if any(re.search(r'\b(?:overview|recap|revision deck|revision snapshot|agenda|thank you)\b|\b\d+\s+(?:mcq\s+)?questions?\b',x,re.I) for x in lines):
                section['classification']='context'
                section['classification_reason']='Explicit cover, overview or recap without question/option markers'
                if current:finish()
                continue
        if not lines:
            errors.append({'row':0,'message':f"{section['label']}: No readable text; vision/OCR review required"});continue
        key_heading=bool(KEY_HEADING.fullmatch(lines[0]))
        # A continued final answer-key slide may omit its heading. Require every
        # line to be an explicit numbered choice/boolean key, never prose.
        key_only=all((entry:=KEY_ENTRY.fullmatch(line)) and re.fullmatch(r'(?:[A-T](?:\s*[,|;]\s*[A-T])*|true|false)(?:[.)]\s+.+)?',entry.group(2),re.I) for line in lines)
        if key_heading or key_only:
            section['classification']='answer_key'
            for line in lines[1:] if key_heading else lines:
                key=KEY_ENTRY.fullmatch(line)
                if key:
                    qid=str(int(key.group(1)))
                    if qid in keys:
                        errors.append({'row':0,'message':f"{section['label']}: Duplicate answer key for question {qid} requires review"})
                    else:keys[qid]=(key.group(2),section['number'])
                else:errors.append({'row':0,'message':f"{section['label']}: Unassociated answer-key content: {line[:180]}"})
            continue
        continuation=bool(OPTION.match(lines[0]) or ANSWER.match(lines[0]) or CHECK.search(lines[0]))
        if current and not continuation: finish()
        for line in lines:
            banner=BANNER.fullmatch(line)
            if banner:
                if sum(bool(OPTION.match(text)) for text in lines)>=2:section['parser_layout_resolved']=True
                if current:finish()
                current_id=str(int(banner.group(1)))
                locations=[section['number']]
                continue
            if re.fullmatch(r'(?:page\s+)?\d+\s*(?:of|/)\s*\d+',line,re.I):continue
            start=START.match(line)
            if start:
                if current:
                    if current_id or any(OPTION.match(x) or ANSWER.match(x) or '?' in x for x in current):finish()
                    else:current=[];locations=[] # Document heading preceding numbered questions.
                id_match=re.search(r'\d+',line.split(start.group(1),1)[0]) if start.group(1) else re.search(r'\d+',line)
                current_id=str(int(id_match.group())) if id_match else None
                current=[start.group(1)] if start.group(1) else []
                locations=[section['number']]
            else:
                if ('?' in line or re.match(r'^(?:True/False|Survey|Poll|Short Answer)\s*:',line,re.I)) and not OPTION.match(line) and not ANSWER.match(line) and any(OPTION.match(x) or ANSWER.match(x) for x in current):finish()
                current.append(line)
                if section['number'] not in locations:locations.append(section['number'])
    finish()
    if len(blocks)>100:raise ValueError('Document imports support at most 100 questions')
    result=[];used_keys=set()
    question_ids=[qid for qid,_,_ in blocks if qid is not None]
    ambiguous_ids={qid for qid in question_ids if question_ids.count(qid)>1}
    for qid in ambiguous_ids:
        errors.append({'row':0,'message':f'Duplicate question number {qid}; separate answer keys cannot be safely associated'})
    for index,(qid,lines,locations) in enumerate(blocks,1):
        if qid in keys and qid not in ambiguous_ids and not any(ANSWER.match(line) for line in lines):
            answer,number=keys[qid];lines=[*lines,'Answer: '+answer];locations=[*locations,number];used_keys.add(qid)
        source={'filename':filename,'sections':locations}
        if format=='pptx':source['slide_number']=locations[0]
        if format=='pdf':source['page_number']=locations[0]
        try:result.append(preview_row(parse_question(lines,source)))
        except (ValueError,ValidationError) as error:
            errors.append({'row':index,'message':f"{'Slide' if format=='pptx' else 'Page' if format=='pdf' else 'Section'} {locations[0]}: {str(error)[:600]}. Extracted text: {' '.join(lines)[:180]}"})
    for key in keys.keys()-used_keys:errors.append({'row':0,'message':f'Answer key for question {key} could not be safely associated or conflicts with an existing answer'})
    return result,errors
