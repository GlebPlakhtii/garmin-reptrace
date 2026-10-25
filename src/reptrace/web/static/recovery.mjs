const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statuses = {
  preview:'Awaiting confirmation', done:'Completed', cancelled:'Cancelled',
  intent:'Ready to continue', local_pending:'Local save pending',
  remote_uncertain:'Garmin result unknown', remote_unresolved:'Garmin needs review',
  running:'In progress', partial:'Partly completed',
};
const steps = {
  saved:'Saved and checked', pending:'Pending', uncertain:'Result unknown',
  unresolved:'Needs review', readback_mismatch:'Saved contents differ',
  not_started:'Not started', not_requested:'Not requested', requested:'Delivery requested',
  failed:'Request rejected',
};
const errors = {
  remote_revision_conflict:'Garmin changed after the confirmed update. Compare the saved preview with Garmin before continuing.',
  remote_readback_failed:'Garmin could not be checked. Continue to check the same operation again.',
  revision_conflict:'Your local workout changed after review. Compare it with the saved preview before continuing.',
  save_failed:'The local save could not be confirmed. Continue to check or finish the same save.',
};
export const operationNeedsAttention = operation => !['preview','done','cancelled'].includes(operation.status);
const label = operation => operation.kind==='creation'?'Create Garmin workouts':`Activity correction${operation.activityId?' · '+operation.activityId:''}`;
const stamp = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('en-GB',{dateStyle:'medium',timeStyle:'short'}) : 'Time unavailable';
const progress = operation => operation.kind==='creation'
  ? `<ul class="operation-items">${(operation.items||[]).map(item=>`<li><strong>${escape(item.name)}</strong><span>${!item.selected?'Not selected':`${escape(steps[item.creation]||'Unknown save status')} · ${escape(steps[item.delivery]||'Unknown delivery status')}`}</span></li>`).join('')}</ul>`
  : `<dl class="operation-progress"><div><dt>Garmin</dt><dd>${escape(steps[operation.remoteStatus]||'Not started')}</dd></div><div><dt>RepTrace</dt><dd>${escape(steps[operation.localStatus]||'Not started')}</dd></div></dl>`;

export function recoveryPage({operations=null,loading=false,error=''}={}) {
  const unfinished=(operations||[]).filter(operationNeedsAttention).length;
  return `<section class="page-heading"><div><div class="eyebrow">GARMIN OPERATIONS</div><h1>Operation recovery<span class="heading-dot">.</span></h1><p>Check activity corrections and new workouts you reviewed in Telegram. Continue an unfinished confirmation from its saved progress.</p></div><button class="button" data-operation-refresh ${loading?'disabled':''}>${loading?'Checking…':'Refresh status'}</button></section>`+
    `<p class="feature-note">This history is read from RepTrace. Refreshing status does not contact Garmin. Delivery requested means queued for the watch; it does not confirm watch sync.</p>`+
    (error?`<div class="refresh-notice" role="alert"><div><strong>${escape(error)}</strong>${operations?'<span>Last loaded status is shown below.</span>':''}</div></div>`:'')+
    `<section class="panel operation-history" aria-busy="${loading}"><div class="table-heading"><div><h2>Recent operations</h2><p>${operations===null?'Checking saved progress…':`${unfinished} need attention · ${(operations||[]).length} recent operations`}</p></div></div>`+
    (operations===null?`<p class="small-empty" role="status">${error?'Use Refresh status to try again.':'Loading operation history…'}</p>`:!operations.length?'<div class="empty-panel"><h3>No saved operations yet</h3><p>Reviewed activity corrections and new workout creations will appear here.</p></div>':
      `<div class="operations-list">${operations.map(operation=>`<article class="operation-card"><div class="operation-card-heading"><h3>${escape(label(operation))}</h3><span class="operation-status ${operationNeedsAttention(operation)?'needs-attention':''}">${escape(statuses[operation.status]||'Needs review')}</span></div><p class="muted">Updated ${escape(stamp(operation.updatedAt))}</p>${progress(operation)}${operation.localError?`<p class="operation-message">${escape(errors[operation.localError]||'Review the saved operation before continuing.')}</p>`:''}<button class="button" data-operation-review="${escape(operation.id)}">Review ${operationNeedsAttention(operation)?'recovery':'details'}</button></article>`).join('')}</div>`)+`</section>`;
}

export function recoveryReview(operation,{busy=false,error=''}={}) {
  const canResume=operation.canResume===true&&operationNeedsAttention(operation);
  const message=operation.status==='preview'?'This preview has not been confirmed. Return to its original preview to choose what to save.':operation.status==='done'?'This operation is complete. No further save is needed.':operation.status==='cancelled'?'This preview was cancelled.':operation.kind==='creation'?'Continue the originally selected workouts. This may finish saving them to Garmin and request delivery to the selected watch. Unknown creation or delivery results are checked before another action is attempted.':operation.destination==='local'?'Continue the same confirmed local correction. Garmin will not be changed.':'Continue the same confirmed correction in Garmin and RepTrace. Garmin is checked before the local save is completed.';
  return `<div class="recovery-review"><div class="dialog-heading"><div><span class="eyebrow">${escape(statuses[operation.status]||'NEEDS REVIEW')}</span><h2 id="editor-title">${escape(label(operation))}</h2></div><button type="button" class="icon-button close-editor" aria-label="Close recovery review" ${busy?'disabled':''}>×</button></div><div class="recovery-review-body"><p>${escape(message)}</p>${operation.deviceName?`<p>Watch: <strong>${escape(operation.deviceName)}</strong></p>`:''}${progress(operation)}${operation.localError?`<p class="operation-message">${escape(errors[operation.localError]||'Review the saved operation before continuing.')}</p>`:''}<h3>Originally reviewed changes</h3><pre class="operation-preview">${escape(operation.preview||'No preview text was saved.')}</pre><p class="muted">Reference: ${escape(operation.id)}</p><p class="form-error" role="alert">${escape(error)}</p></div><div class="dialog-footer"><button class="button close-editor" ${busy?'disabled':''}>Close</button>${canResume?`<button class="button button-dark" data-operation-resume="${escape(operation.id)}" ${busy?'disabled':''}>${busy?'Checking progress…':'Check and continue'}</button>`:''}</div></div>`;
}
