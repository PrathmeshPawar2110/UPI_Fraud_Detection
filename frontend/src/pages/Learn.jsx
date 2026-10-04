import { useState } from "react";
import { Link } from "react-router";
import { PageHead } from "../components/ui.jsx";

export const SCAMS = [
  { id: "upi", title: "UPI collect & 'receive' tricks", how: "You get a payment request or QR and are told to approve it or enter your PIN to receive money.",
    flags: ["'Enter PIN to receive'", "A collect request from someone you don't know", "A QR sent over chat to 'get a refund'"],
    act: "Decline. Receiving money never needs a PIN or a scan." },
  { id: "screenshot", title: "Fake payment screenshots", how: "A buyer shows a 'payment successful' screenshot and rushes you to hand over goods; no money ever arrives.",
    flags: ["Pressure to hand over goods immediately", "Credit not visible in your bank app or SMS", "Edited fonts or amounts"],
    act: "Check your bank app or SMS, not the screenshot, before handing anything over." },
  { id: "kyc", title: "KYC update scams", how: "An SMS says your account or SIM will be blocked unless you update KYC through a link or a call.",
    flags: ["Threat of blocking 'today'", "Link that isn't your bank's domain", "Asks for OTP or app install"],
    act: "Banks don't do KYC through SMS links. Visit the branch or the official app. Report the SMS on Chakshu." },
  { id: "otp", title: "OTP scams", how: "Someone posing as bank, delivery or support staff asks you to 'confirm' an OTP that actually approves a payment or login.",
    flags: ["Anyone asking you to read out an OTP", "'Just to verify your identity'"],
    act: "Never share an OTP with anyone, including people claiming to be from your bank." },
  { id: "qr", title: "QR code scams", how: "A QR promises cashback or a prize, or a shop's QR is covered by a fraudster's sticker.",
    flags: ["'Scan to receive'", "Payee name doesn't match the shop", "Pre-filled amount you didn't agree to"],
    act: "Scanning always sends money. Check the payee name in your app before approving." },
  { id: "remote", title: "Remote-access scams", how: "A 'support agent' asks you to install AnyDesk, TeamViewer or a similar app and then controls your phone.",
    flags: ["Request to install a screen-sharing app", "Asked to share a 9-digit code"],
    act: "Uninstall the app, change your UPI PIN and passwords, and call your bank." },
  { id: "investment", title: "Investment & task scams", how: "A group promises guaranteed returns or pays small amounts for 'tasks', then asks for bigger deposits.",
    flags: ["Guaranteed or very high returns", "You must pay to withdraw 'profits'", "Telegram / WhatsApp 'VIP groups'"],
    act: "Stop paying. Withdrawals that need a fee are a sign of fraud. Report at cybercrime.gov.in." },
  { id: "wrong", title: "Wrong-transfer scams", how: "A stranger 'accidentally' sends money (or a fake credit SMS) and pressures you to return it, often to another account.",
    flags: ["Urgent request to send it back", "Return to a different UPI ID", "Credit not visible in your bank"],
    act: "Don't send money back yourself. Ask them to raise it with their bank, which reverses genuine mistakes." },
  { id: "support", title: "Fake customer care", how: "You search for a helpline online and call a scammer's number listed on a fake page or review site.",
    flags: ["Helpline found through search ads or social media", "Asked for UPI PIN, OTP or a 'verification payment'"],
    act: "Only use numbers from the official app, website or the back of your card." },
  { id: "social", title: "Social engineering & digital arrest", how: "Callers pose as police, CBI, customs or a courier, claim you're involved in a crime and demand money to 'clear' you.",
    flags: ["Video calls from 'officers'", "Threats of arrest", "Instructions to stay on the call and not tell anyone"],
    act: "Police never arrest you over a call or ask for money. Hang up and call 1930." },
];

const QUIZ = [
  { q: "An SMS: 'Your SBI KYC has expired, your account will be blocked today. Update at http://sbi-kyc-update.example'. Fraud or legitimate?",
    a: "fraud", why: "Threat + deadline + a link that isn't SBI's domain. Banks don't do KYC through SMS links." },
  { q: "You paid ₹240 at your usual tea stall, at 4 pm, to the same UPI ID you've paid 30 times before. Fraud or legitimate?",
    a: "legit", why: "Small, routine amount to a long-known recipient at your usual time: nothing unusual." },
  { q: "Someone says they sent you ₹5,000 by mistake. Your bank app doesn't show it. They ask you to send it to another UPI ID. Fraud or legitimate?",
    a: "fraud", why: "No credit in your bank, a different UPI ID and pressure to pay: a wrong-transfer scam. Genuine mistakes are reversed by banks." },
  { q: "A QR at a shop shows payee 'Sharma General Store', the same name as the shop, and no pre-filled amount. Fraud or legitimate?",
    a: "legit", why: "Payee name matches the shop and you enter the amount yourself. Still check the name in your app each time." },
  { q: "A 'PhonePe support' number asks you to install AnyDesk so they can fix a failed refund. Fraud or legitimate?",
    a: "fraud", why: "Real support never asks you to install screen-sharing apps. That would give them control of your phone." },
];

export default function Learn() {
  const [open, setOpen] = useState(null);
  const [answers, setAnswers] = useState({});
  const score = Object.entries(answers).filter(([i, a]) => QUIZ[i].a === a).length;

  return (
    <>
      <PageHead kicker="Learn" title="Common UPI scams">
        How each scam works, the red flags, and what to do. Every scam here also appears in the <Link to="/simulator">simulator</Link>.
      </PageHead>
      <ul className="learn-grid">
        {SCAMS.map((s) => (
          <li key={s.id} className={open === s.id ? "open" : ""}>
            <button type="button" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
              <span>{s.title}</span><span aria-hidden="true">{open === s.id ? "−" : "+"}</span>
            </button>
            {open === s.id && (
              <div className="learn-body">
                <p>{s.how}</p>
                <p className="label">Red flags</p>
                <ul className="plain">{s.flags.map((f) => <li key={f}>{f}</li>)}</ul>
                <p className="label">What to do</p>
                <p>{s.act}</p>
              </div>
            )}
          </li>
        ))}
      </ul>

      <section className="sec">
        <div className="sec-head"><span className="sec-no">Quiz</span><h2>Fraud or legitimate?</h2>
          <span className="sec-aside">{Object.keys(answers).length}/{QUIZ.length} answered · {score} correct</span></div>
        <ol className="quiz">
          {QUIZ.map((item, i) => (
            <li key={i}>
              <p>{item.q}</p>
              <div className="row-actions" role="group" aria-label={`Question ${i + 1}`}>
                {[["fraud", "Fraud"], ["legit", "Legitimate"]].map(([v, t]) => (
                  <button key={v} type="button" className={"pill" + (answers[i] === v ? " on" : "")} aria-pressed={answers[i] === v}
                          onClick={() => setAnswers({ ...answers, [i]: v })}>{t}</button>
                ))}
              </div>
              {answers[i] && (
                <p className={"quiz-feedback " + (answers[i] === item.a ? "right" : "wrong")} role="status">
                  <b>{answers[i] === item.a ? "Correct." : "Not quite."}</b> {item.why}
                </p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
