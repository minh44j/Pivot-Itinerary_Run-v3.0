/**
 * Pivot — "Manual itinerary" Google Form (one-time setup).
 *
 * HOW TO RUN (once, as the person who will own the form — e.g. Minhaj):
 *   1. Open https://script.google.com  →  New project  →  paste this whole file  →  Save.
 *   2. Choose the function  createManualItineraryForm  in the toolbar  →  Run.
 *   3. Approve the permissions (Forms, Sheets, Drive). Open  View → Logs  and copy the two links:
 *        FORM  (give to the ticketing executives — bookmark it)
 *        SHEET (the responses; already shared with the automation's mailbox)
 *   4. Put the SHEET's id (the long text between /d/ and /edit in its URL) into the GitHub secret
 *      MANUAL_SHEET_ID. Optionally put the FORM link into MANUAL_FORM_URL (it is added to "fix it" e-mails).
 *
 * The question TITLES below are a contract with manual_sheet.py (the runner reads the sheet by title).
 * Do not rename a title without changing manual_sheet.py; a test checks they match.
 */
var RUNNER_USER = 'cs@pivottmc.com';        // the mailbox the automation impersonates; gets Editor on the Sheet
var MAX_PASSENGERS = 4;
var MAX_FLIGHTS = 6;
var TITLES = ['Mr', 'Mrs', 'Ms', 'Miss', 'Mstr', 'Dr'];
var CABINS = ['Economy', 'Premium Economy', 'Business', 'First'];

function createManualItineraryForm() {
  var form = FormApp.create('Pivot — Manual itinerary');
  form.setDescription(
    'For tickets that do not arrive automatically (a partner or an airline you issue by hand).\n\n' +
    'Type what is printed on the ticket — nothing is guessed. Submit, and the finished itinerary PDF is e-mailed to YOU ' +
    'within a few minutes. If something is wrong you get an e-mail saying exactly what to fix. ' +
    'Check the PDF against the ticket, then forward it to the client.');
  form.setCollectEmail(true);          // we reply to whoever submitted
  form.setRequireLogin(true);          // only people in the Workspace
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage(
    'Received. The itinerary PDF will arrive in your inbox in a few minutes. ' +
    'No e-mail after 15 minutes? Check Spam, then tell Minhaj.');

  var pnrRule = FormApp.createTextValidation().setHelpText('5 to 8 letters or digits, e.g. 9YP3RJ')
      .requireTextMatchesPattern('^[A-Za-z0-9]{5,8}$').build();
  var iataRule = FormApp.createTextValidation().setHelpText('3 letters, e.g. RUH')
      .requireTextMatchesPattern('^[A-Za-z]{3}$').build();
  var timeRule = FormApp.createTextValidation().setHelpText('24-hour time like 18:05')
      .requireTextMatchesPattern('^([01]?[0-9]|2[0-3]):[0-5][0-9]$').build();
  var tktRule = FormApp.createTextValidation().setHelpText('10 to 14 digits, no spaces')
      .requireTextMatchesPattern('^[0-9]{10,14}$').build();
  var flightNoRule = FormApp.createTextValidation().setHelpText('Airline code + number, e.g. SV 774')
      .requireTextMatchesPattern('^[A-Za-z0-9]{2}\\s?-?\\s?[0-9]{1,4}[A-Za-z]?$').build();
  var seatRule = FormApp.createTextValidation().setHelpText('Row + letter, e.g. 14A')
      .requireTextMatchesPattern('^[0-9]{1,3}[A-Za-z]$').build();

  function text(title, help, required, rule) {
    var it = form.addTextItem().setTitle(title).setRequired(!!required);
    if (help) it.setHelpText(help);
    if (rule) it.setValidation(rule);
    return it;
  }
  function date(title, help, required) {
    var it = form.addDateItem().setTitle(title).setIncludesYear(true).setRequired(!!required);
    if (help) it.setHelpText(help);
    return it;
  }

  // ───────── page 1: the booking + passenger 1 ─────────
  form.addSectionHeaderItem().setTitle('The booking');
  text('PNR', 'The booking reference printed on the ticket.', true, pnrRule);
  text('Agency reference', 'Optional — only if the ticket shows one.', false);
  text('CRS reference', 'Optional — only if the ticket shows one.', false);
  date('Booked on', 'Optional — the booking date, only if the ticket shows it. Leave empty if it does not (the PDF will say N/A).', false);

  var addPaxItems = [];      // "Add another passenger?" items, wired to pages after all pages exist
  var paxPages = [];
  function passengerBlock(n) {
    form.addSectionHeaderItem().setTitle('Passenger ' + n);
    form.addListItem().setTitle('Passenger ' + n + ' - Title').setChoiceValues(TITLES).setRequired(n === 1);
    text('Passenger ' + n + ' - Given name(s)', 'First and middle names, as on the ticket.', n === 1);
    text('Passenger ' + n + ' - Surname', 'Family name, as on the ticket.', n === 1);
    text('Passenger ' + n + ' - Ticket number', 'The e-ticket number, digits only.', n === 1, tktRule);
    if (n < MAX_PASSENGERS) {
      addPaxItems.push({ n: n, item: form.addMultipleChoiceItem().setTitle('Passenger ' + n + ' - Add another passenger?').setRequired(true) });
    }
  }
  passengerBlock(1);
  for (var p = 2; p <= MAX_PASSENGERS; p++) {
    paxPages.push(form.addPageBreakItem().setTitle('Passenger ' + p));
    passengerBlock(p);
  }

  // ───────── flights ─────────
  var flightPages = [];
  var addFlightItems = [];
  for (var f = 1; f <= MAX_FLIGHTS; f++) {
    flightPages.push(form.addPageBreakItem().setTitle('Flight ' + f).setHelpText(
        f === 1 ? 'Enter flights in travel order. Connecting flights are separate flights.' : ''));
    var P = 'Flight ' + f + ' - ';
    text(P + 'Flight number', 'Airline code + number, e.g. SV 774', true, flightNoRule);
    text(P + 'Operated by (airline)', 'The airline name as it should print, e.g. Saudia', true);
    text(P + 'From (airport code)', '3-letter code, e.g. RUH', true, iataRule);
    text(P + 'From city', 'e.g. Riyadh', true);
    text(P + 'To (airport code)', '3-letter code, e.g. COK', true, iataRule);
    text(P + 'To city', 'e.g. Cochin', true);
    date(P + 'Departure date', null, true);
    text(P + 'Departure time', 'Local time at the departure airport, 24-hour, e.g. 11:35', true, timeRule);
    date(P + 'Arrival date', 'Local date at the arrival airport.', true);
    text(P + 'Arrival time', 'Local time at the arrival airport, 24-hour, e.g. 18:50', true, timeRule);
    form.addListItem().setTitle(P + 'Cabin class').setChoiceValues(CABINS).setRequired(true);
    text(P + 'Departure terminal', 'Optional — only if the ticket states it.', false);
    text(P + 'Arrival terminal', 'Optional — only if the ticket states it.', false);
    text(P + 'Duration', 'Optional, e.g. 4h 45m', false);
    text(P + 'Cabin baggage', 'Optional, as printed — e.g. 7kg', false);
    text(P + 'Checked baggage', 'Optional, as printed — e.g. 2 pieces, or 30kg', false);
    text(P + 'Airline reference', 'Optional — ONLY if this flight has its own reference different from the PNR above (two airlines on one ticket).', false);
    for (var k = 1; k <= MAX_PASSENGERS; k++) {
      text(P + 'Seat, passenger ' + k, k === 1 ? 'Optional — leave empty if no seat is assigned. One box per passenger, in the order entered above.' : 'Optional', false, seatRule);
    }
    if (f < MAX_FLIGHTS) {
      addFlightItems.push({ f: f, item: form.addMultipleChoiceItem().setTitle(P + 'Add another flight?').setRequired(true) });
    }
  }

  // ───────── branching (every page exists now) ─────────
  var firstFlight = flightPages[0];
  addPaxItems.forEach(function (o) {
    var yes = o.item.createChoice('Yes — add passenger ' + (o.n + 1), FormApp.PageNavigationType.CONTINUE);
    var no = o.item.createChoice('No — go to the flights', firstFlight);
    o.item.setChoices([yes, no]);
  });
  addFlightItems.forEach(function (o) {
    var yes = o.item.createChoice('Yes — add flight ' + (o.f + 1), FormApp.PageNavigationType.CONTINUE);
    var no = o.item.createChoice('No — submit', FormApp.PageNavigationType.SUBMIT);
    o.item.setChoices([yes, no]);
  });

  // ───────── the response sheet, shared with the automation's mailbox ─────────
  var ss = SpreadsheetApp.create('Pivot — Manual itinerary (responses)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  try { ss.addEditor(RUNNER_USER); } catch (e) { Logger.log('Could not share the sheet with ' + RUNNER_USER + ': ' + e); }

  Logger.log('FORM  (share this with the executives): ' + form.getPublishedUrl());
  Logger.log('FORM  (edit):                            ' + form.getEditUrl());
  Logger.log('SHEET (responses):                       ' + ss.getUrl());
  Logger.log('SHEET id for the GitHub secret MANUAL_SHEET_ID: ' + ss.getId());
}
