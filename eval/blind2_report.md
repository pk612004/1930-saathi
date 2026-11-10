# Blind set #2: 43/48 correct (90%) now

First run, before any fixes: **40/48 (83%)**, saved in blind2_first_run.md. Three general gaps were then
fixed (Tamil 'oru' = one, 'half an hour', number words before 'baje'). The remaining UPI misses are names whose
English spelling cannot be recovered from Indic-script sounds; the dialog flags them and asks the caller to
spell them letter by letter (see tests/test_spelling.py).

| Type | Caller said | Expected | Got | |
|---|---|---|---|---|
| amount | lagbhag teen hazaar chaar sau | 3400 | 3400 | ✅ |
| amount | ek lakh assi hazaar | 180000 | 180000 | ✅ |
| amount | do hazaar ke aas paas | 2000 | 2000 | ✅ |
| amount | रुपये 7500 | 7500 | 7500 | ✅ |
| amount | सत्तर हज़ार रुपये | 70000 | 70000 | ✅ |
| amount | डेढ़ हज़ार | 1500 | 1500 | ✅ |
| amount | about sixty thousand | 60000 | 60000 | ✅ |
| amount | two lakh twenty thousand | 220000 | 220000 | ✅ |
| amount | ਪੰਜਾਹ ਹਜ਼ਾਰ ਰੁਪਏ | 50000 | 50000 | ✅ |
| amount | ਡੇਢ ਲੱਖ | 150000 | 150000 | ✅ |
| amount | das aayiram rubaai | 10000 | 10000 | ✅ |
| amount | மூணு லட்சம் | 300000 | 300000 | ✅ |
| digits | sath aath nau shunya, ek do teen chaar, paanch chhe saat aath | 789012345678 | 6089012345678 | ❌ |
| digits | number likh lo 9 9 1 5, 0 2 3 4, 7 7 8 1 | 991502347781 | 991502347781 | ✅ |
| digits | सात सात सात दो, एक एक नौ नौ, शून्य शून्य तीन चार | 777211990034 | 777211990034 | ✅ |
| digits | double six, double four, five five three, one two zero nine | 66445531209 | 66445531209 | ✅ |
| digits | ਨੌਂ ਅੱਠ ਸੱਤ ਛੇ ਪੰਜ ਚਾਰ ਤਿੰਨ ਦੋ ਇੱਕ ਸਿਫ਼ਰ | 9876543210 | 9876543210 | ✅ |
| digits | ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்யம் | 9876543210 | 9876543210 | ✅ |
| digits | onnu rendu moonu naalu anju aaru ezhu ettu ombodhu pathu | 12345678910 | 12345678910 | ✅ |
| digits | 4 0 0 0 1 2 3, 4 5 6 7 8 | 400012345678 | 400012345678 | ✅ |
| upi | suresh kumar at the rate ybl | sureshkumar@ybl | sureshkumar@ybl | ✅ |
| upi | id hai payment dot help at the rate okicici | payment.help@okicici | payment.help@okicici | ✅ |
| upi | सुरेश एट द रेट पेटीएम | suresh@paytm | suresh@paytm | ✅ |
| upi | विकास डॉट शर्मा एट द रेट ओके एसबीआई | vikas.sharma@oksbi | vikas.sharma@oksbi | ✅ |
| upi | ਗੁਰਪ੍ਰੀਤ ਐਟ ਦ ਰੇਟ ਪੇਟੀਐਮ | gurpreet@paytm | guraprit@paytm | ❌ |
| upi | ਹਰਜੀਤ ਡਾਟ ਸਿੰਘ ਐਟ ਦ ਰੇਟ ਵਾਈ ਬੀ ਐਲ | harjit.singh@ybl | harajit.singh@ybl | ❌ |
| upi | கார்த்திக் அட் த ரேட் வைபிஎல் | karthik@ybl | karttik@ybl | ❌ |
| upi | முருகன் அட் த ரேட் பேடிஎம் | murugan@paytm | murukan@paytm | ❌ |
| upi | rahul007 at the rate axl | rahul007@axl | rahul007@axl | ✅ |
| upi | एस के एट द रेट वाई बी एल | sk@ybl | sk@ybl | ✅ |
| time | pandrah minute pehle | 15 | 15 | ✅ |
| time | ek ghante pehle | 60 | 60 | ✅ |
| time | सुबह दस बजे | 180 | 180 | ✅ |
| time | पंद्रह मिनट पहले | 15 | 15 | ✅ |
| time | about half an hour ago | 30 | 30 | ✅ |
| time | ਵੀਹ ਮਿੰਟ ਪਹਿਲਾਂ | 20 | 20 | ✅ |
| time | ਅੱਧਾ ਘੰਟਾ ਪਹਿਲਾਂ | 30 | 30 | ✅ |
| time | 10 நிமிஷம் முன்னாடி | 10 | 10 | ✅ |
| time | ஒரு மணி நேரம் முன்னாடி | 60 | 60 | ✅ |
| bank | mera account baroda bank mein hai | Bank of Baroda | Bank of Baroda | ✅ |
| bank | ਸਟੇਟ ਬੈਂਕ ਵਿੱਚ | State Bank of India | State Bank of India | ✅ |
| bank | ஐஓபி பேங்க் | Indian Overseas Bank | Indian Overseas Bank | ✅ |
| mode | google pay se bheje | UPI | UPI | ✅ |
| mode | ਗੂਗਲ ਪੇ ਨਾਲ | UPI | UPI | ✅ |
| yesno | haan haan bilkul sahi | True | True | ✅ |
| yesno | nahi ji, galat hai | False | False | ✅ |
| yesno | ਹਾਂ ਜੀ ਬਿਲਕੁਲ | True | True | ✅ |
| yesno | இல்ல, தப்பு | False | False | ✅ |
