param name string
param location string = resourceGroup().location
param tags object = {}

@description('Application Insights resource used for the agent\'s own logs')
param appInsightsId string
param appInsightsAppId string
@secure()
param appInsightsConnectionString string

@description('Grant the deploying user the SRE Agent Administrator role on the agent')
param grantDeployerAdmin bool = true

var sreAgentAdministratorRoleId = 'e79298df-d852-4c6d-84f9-5d13249d1e55'

// Roles the agent's managed identity gets on this resource group only (least privilege)
var agentRoles = [
  'acdd72a7-3385-48ef-bd42-f606fba81ae7' // Reader
  '43d0d8ad-25c7-4714-9337-8ba259a9fe05' // Monitoring Reader
  '749f88d5-cbae-40b8-bcfc-e573ddc772fa' // Monitoring Contributor
  '73c42c96-874c-492b-b04d-ab87d138a893' // Log Analytics Reader
  '358470bc-b998-42bd-ab17-a7e34c199c0f' // Container Apps Contributor
]

resource agentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-${name}'
  location: location
  tags: tags
}

resource agentRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in agentRoles: {
  name: guid(resourceGroup().id, agentIdentity.id, roleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

#disable-next-line BCP081
resource sreAgent 'Microsoft.App/agents@2025-05-01-preview' = {
  name: name
  location: location
  tags: union(tags, {
    'hidden-link: /app-insights-resource-id': appInsightsId
  })
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${agentIdentity.id}': {}
    }
  }
  properties: {
    knowledgeGraphConfiguration: {
      managedResources: [
        resourceGroup().id
      ]
      identity: agentIdentity.id
    }
    actionConfiguration: {
      mode: 'autonomous'
      identity: agentIdentity.id
      accessLevel: 'Low'
    }
    mcpServers: []
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: appInsightsAppId
        connectionString: appInsightsConnectionString
      }
    }
  }
  dependsOn: [
    agentRoleAssignments
  ]
}

resource deployerAdminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantDeployerAdmin) {
  name: guid(sreAgent.id, deployer().objectId, sreAgentAdministratorRoleId)
  scope: sreAgent
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sreAgentAdministratorRoleId)
    principalId: deployer().objectId
  }
}

output id string = sreAgent.id
output name string = sreAgent.name
output endpoint string = sreAgent.properties.agentEndpoint
output identityPrincipalId string = agentIdentity.properties.principalId
