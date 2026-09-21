// Google Apps Script web app that emails each feedback message from the trainer.
// Deploy: script.google.com → New project → paste → Deploy → New deployment →
// Web app, "Execute as: Me", "Who has access: Anyone" → copy the URL into
// firebase-config.js as feedbackHook. Runs under the account that deploys it,
// so the mail comes from that Gmail (quota 100 mails a day).
const TO = 'vladyslav1595@gmail.com';

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  const body = [
    'Від: ' + (d.name || '') + ' <' + (d.email || '') + '>',
    'Сторінка: ' + (d.context || '—'),
    'Браузер: ' + (d.ua || ''),
    'Час: ' + (d.createdAt || ''),
    '',
    d.text || '(без тексту)',
  ].join('\n');
  const opts = { name: 'ТЗНК тренажер' };
  const m = /^data:(image\/(\w+));base64,(.*)$/.exec(d.image || '');
  if (m) opts.attachments = [Utilities.newBlob(Utilities.base64Decode(m[3]), m[1], 'screenshot.' + m[2])];
  MailApp.sendEmail(TO, 'ТЗНК тренажер: відгук від ' + (d.name || d.email || '?'), body, opts);
  return ContentService.createTextOutput('ok');
}
