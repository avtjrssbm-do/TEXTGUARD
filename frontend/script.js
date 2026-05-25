const API="http://127.0.0.1:8000";

async function uploadDatabase(){

const files=
document.getElementById(
"databaseFolder"
).files;

if(files.length===0){

alert(
"Выберите файлы"
);

return;

}

const formData=
new FormData();

for(let i=0;i<files.length;i++){

formData.append(
"files",
files[i]
);

}

const response=
await fetch(

API+"/upload_database",

{
method:"POST",
body:formData
}

);

const data=
await response.json();

alert(
"Добавлено: "+data.count
);

}



async function loadDatabaseLink(){

const url=
document.getElementById(
"dbLink"
).value;

if(!url){

alert(
"Введите ссылку"
);

return;

}

const response=
await fetch(

API+"/load_database_link",

{

method:"POST",

headers:{
"Content-Type":"application/json"
},

body:JSON.stringify({

url:url

})

}

);

const data=
await response.json();

alert(
data.message
);

}