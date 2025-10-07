Getting a google dialogflow key
======================

To use google dialogflow or other services, you need an authentication JSON key. This can be a little bothersome to set up without a credit card, but if you follow these instructions you should be able to.
For instructions on how to use google dialogflow, please refer to :doc:``

Prerequisites
----------------------------
A Google account

.. note::

    Please take note of which of your google accounts you use to create the service account and/or sign into the dialogflow webpage. This account must be the same one.

Getting a key file
----------------------------
1. **Create a project**
Using the following link, create a project:
https://console.cloud.google.com/projectselector2/home/dashboard

2. **Enable the dialogflow API**
Ensure you have the right project and enable the API
https://console.cloud.google.com/flows/enableapi?apiid=dialogflow.googleapis.com

3. **Create service account**
Go to https://console.cloud.google.com/iam-admin/serviceaccounts and click on the project you just created, then click “Create service account” in the top bar
Follow the instructions, and grant it the following roles
 - Dialogflow API Client
 - Dialogflow API Reader

4. **Create account key**
In the service accounts view, click the service account you have just created. 
In the top bar select “Keys” and select “Add key” To create a new one. Select JSON.
And thats it! This should download the json file with your key.

5. **Create dialogflow agent**
Go to `Dialogflow <https://dialogflow.cloud.google.com/#/getStarted>`_ and sign in with the same google account. Select “Create new agent”. Under the google project drop down make sure to select the same project as the one you created the key for. 

.. note::

    If you selected “create new project” you will have to create a new key for this google project, or create a new agent connected to the right project.

If everything went right, you should have have a ``your_dialogflow_key.json`` with similar content:

.. code-block:: yaml

    {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "348e1399234328ea8ase5e4799a98356ef6ab6",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhk ... lots of characters ... WrXM145A0W1Gm0jZhnI1\n-----END PRIVATE KEY-----\n",
        "client_email": "test-357@test-project.iam.gserviceaccount.com",
        "client_id": "113588749577095165520",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test-357%40test-project.iam.gserviceaccount.com"
    }

Troubleshooting
----------------------------
*No DesignTimeAgent found*: Make sure you are using the right google project for your dialogflow project. Ensure that the service account key you have downloaded is *for the same google project* listed as the connected google project for your dialogflow agent. 

You can find which google project your dialogflow agent is linked to under the agent settings `Dialogflow <https://dialogflow.cloud.google.com/#/getStarted>`_

You can find which google project your json key is for by looking at the ``project_id`` field of the json. In the example key above that is ``"test-project"``.

Useful links for further troubleshooting:
`Quickstart: Setup page for Google Cloud Dialogflow ES <https://cloud.google.com/dialogflow/docs/quick/setup>`_
