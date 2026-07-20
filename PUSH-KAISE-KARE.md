# Ye folder GitHub par kaise chadhega

Do raste. Pehla aasaan hai.

## Rasta 1 - browser se (git install nahi chahiye)

1. github.com/yogibhagwat07/hindi-explainer-pipeline kholo
2. "Add file" -> "Upload files"
3. is folder ke ANDAR ki saari cheezein drag karo:
   README.md, LICENSE, .gitignore, .env.example, tools/, docs/
   (folder khud mat drag karo - uske andar ka saamaan drag karo)
4. neeche "Commit changes"

Note: browser upload me kabhi-kabhi .gitignore jaisi dot-file nahi
chadhti. Na chadhe to "Add file" -> "Create new file" se naam
.gitignore likh kar content paste kar do.

## Rasta 2 - command line se (git chahiye)

```
cd is-folder-ka-rasta
git init
git add .
git commit -m "pipeline tools + docs"
git branch -M main
git remote add origin https://github.com/yogibhagwat07/hindi-explainer-pipeline.git
git pull origin main --allow-unrelated-histories
git push -u origin main
```

Password ki jagah GitHub ab Personal Access Token maangta hai.
Woh tumhare haath se hi banega aur tumhare paas hi rahega - main
kabhi koi password ya token nahi maangunga, na loonga.

## Chadhane ke baad

Repo ko wapas Private kar sakte ho:
Settings -> neeche Danger Zone -> Change visibility -> Private
Public karne se sirf padhna khula tha, likhna phir bhi band tha -
isliye public rakhne ka koi fayda nahi hai.
