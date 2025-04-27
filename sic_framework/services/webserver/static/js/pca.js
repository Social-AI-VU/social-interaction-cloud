/** 
 * Javascript code for the Project Conversational Agents course.
 * 
 * This code makes some basic assumptions about the interaction protocol:
 * - User always is the first to say something (by turning on the microphone)
 * - The microphone automatically is closed again when a transcript has been received (the user has said something)
 * - After receiving a transcript, the turn is given to the agent and the user cannot turn on the microphone.
 * - When the agent has said something, the turn is handed back to the user.
 * 
 * This code also makes assumptions about the names of two buttons: the 'start' and 'mic'(rophone) button.
 * Button clicks are passed on to the webserver, which passes them on to the MARBEL agent using an EIS connector.
 * 
 * Finally, on pages where there is a microphone, a footer should be present with a <p> element with id="transcript".
 * This element will be used to display the transcript received from the ASR component.
 * 
 * SocketIO is used to communicate with the server.
*/

"use strict";

// Establish a WebSocket connection with the Flask server
var socket = io();

// Flag to keep track of whose turn it is (true --> user, false --> agent)
// Initially, it is the agent's turn; DO NOT CHANGE here, this flag is set by EISComponent in SIC framework
var user_turn = false;

// Variable to keep track of number of recipes that fullfill criteria
var recipecounter = -1;

// Code for handling button elements on page
var elements = document.getElementsByClassName("btn");

// Send button clicks to server
var sendButtonClick = function() {
    var name = this.getAttribute("id");
    socket.emit('buttonClick', name); // send button name to web server
};

for (var i = 0; i < elements.length; i++) {
    elements[i].addEventListener('click', sendButtonClick, false);
}

// Dedicated event listeners for two SPECIAL BUTTONS: the 'mic' button.
// Event listener for the mic button to toggle from off to on
// - We need to check if button is available on the webpage, as this may not be the case, e.g. not on start webpage.
// - The socket handler for 'transcript' event turns it off again, see below.
var micButton = document.getElementById('mic');

if (micButton) {
    micButton.addEventListener('click', function() {
        if (user_turn) {
            document.getElementById('micimg').src  = 'static/images/mic_on.png';
        } else {
            alert("It is not your turn.")
        }
    });
}

// Event handler for successful connection
socket.on('connect', function() {
    console.log('Connected to the server.');
});

// Event handler for connection errors
socket.on('connect_error', function(error) {
    console.log('Connection error:', error);
});

// Event handler for disconnection
socket.on('disconnect', function() {
    console.log('Disconnected from the server.');
});

// Event handler for transcript event
socket.on("transcript", (text) => {
    document.getElementById("transcript").innerHTML = text;
});

socket.on("pattern", (pattern) => {
    switch(pattern) {
        case "start":
            window.location.href = "start.html";
            break;
        case "c10":
            window.location.href = "welcome.html";
            break;
        case "a50recipeSelect":
            window.location.href = "recipe_overview.html";
            break;
        default:
          window.location.href = "closing.html";
      }
})

// Event handler for switching turns
socket.on("set_turn", (whoseturn) => {
    if (whoseturn=="true") {
        user_turn = true;
    } else {
        user_turn = false;
    }
    // If it's not the user's turn (any more), then make sure the microphone icon is mic_out
    if (!user_turn) {
        document.getElementById('micimg').src  = 'static/images/mic_out.png';
    }
})

socket.on("recipecounter", (number) => {
    recipecounter = number;
    document.getElementById("recipecounter").innerHTML = recipecounter;
})

// Example showing how to work with templates
// Adding filters to a card deck on an HTML page
socket.on("filters", (filterString) => {
    const filtersString = filterString.substring(1, filterString.length-1);
    if (filterString.length != 0) {
        const filters = filtersString.split(',');
        document.getElementById("addFiltersHere").innerHTML = "";
        filters.forEach((element) => {
            filterCard(element);
        });
    }
})

// Create and add a single card for a filter based on the template in the HTML file
// See also https://www.w3schools.com/tags/tag_template.asp
function filterCard(filter) {
    let filterTemplate = document.querySelector('#filterCardTemplate');
    const card = filterTemplate.content.cloneNode(true);
    card.querySelector('#filterText').innerHTML = filter;
    document.getElementById("addFiltersHere").appendChild(card);
}