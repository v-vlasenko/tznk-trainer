// Public web config of the Firebase project (safe to commit: access is limited by
// Firestore rules and by the authorized domains of the Auth project).
window.TZNK_FIREBASE = {
  firebase: {
    apiKey: "AIzaSyBDm-CFh4i1lifnciZy4Xz6GCmyo_6zo8k",
    authDomain: "tznk-trainer.firebaseapp.com",
    projectId: "tznk-trainer",
    appId: "1:1095506791574:web:7792b049e71f8468ab86b7",
  },
  // Google accounts that may open "Прогрес усіх". Keep in sync with firestore.rules.
  admins: ["vladyslav1595@gmail.com"],
  // Apps Script web app that emails each feedback message (see feedback-hook.gs). Empty: Firestore only.
  feedbackHook: "https://script.google.com/macros/s/AKfycbyugs_7mzRuo38qcLLh7KGBuFymhGrGaeyIzh6rXwKWrpD3WG4GFAkNf7LLF5KCY3hyJw/exec",
};
