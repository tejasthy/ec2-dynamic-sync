"""
AWS EC2 Instance Management for EC2 Dynamic Sync.

This module handles all AWS EC2 operations including:
- Instance discovery and state management
- Dynamic IP resolution
- Instance start/stop operations
- Health checks and monitoring
- Cost tracking and optimization
"""

import boto3
import time
import logging
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError, NoCredentialsError

from .models import AWSConfig
from .exceptions import AWSConnectionError, InstanceNotFoundError, PermissionError


class AWSManager:
    """Manages AWS EC2 operations for the sync system."""
    
    def __init__(self, aws_config: AWSConfig):
        """Initialize AWS manager with configuration.
        
        Args:
            aws_config: AWS configuration object
            
        Raises:
            AWSConnectionError: If AWS connection fails
        """
        self.config = aws_config
        self.logger = logging.getLogger(__name__)
        
        # Initialize AWS client
        try:
            session = boto3.Session(profile_name=self.config.profile)
            self.ec2_client = session.client('ec2', region_name=self.config.region)
            self.ec2_resource = session.resource('ec2', region_name=self.config.region)
            
            # Test connection
            self._test_connection()
            
        except NoCredentialsError as e:
            raise AWSConnectionError(
                "AWS credentials not found. Please configure AWS CLI with 'aws configure'.",
                aws_error_code="NoCredentialsError",
                region=self.config.region,
                profile=self.config.profile
            ) from e
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise AWSConnectionError(
                f"AWS connection failed: {e}",
                aws_error_code=error_code,
                region=self.config.region,
                profile=self.config.profile
            ) from e
        except Exception as e:
            raise AWSConnectionError(
                f"Failed to initialize AWS client: {e}",
                region=self.config.region,
                profile=self.config.profile
            ) from e
    
    def _test_connection(self):
        """Test AWS connection and permissions."""
        try:
            # Simple test to verify connection and basic permissions
            self.ec2_client.describe_regions(RegionNames=[self.config.region])
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                raise PermissionError(
                    "Insufficient AWS permissions. Please ensure your credentials have EC2 access.",
                    resource_type="aws_service",
                    required_permissions=["ec2:DescribeRegions", "ec2:DescribeInstances"]
                )
            raise
    
    def get_instance_id(self) -> Optional[str]:
        """Get the EC2 instance ID from config or by name tag.
        
        Returns:
            Instance ID if found, None otherwise
            
        Raises:
            InstanceNotFoundError: If instance cannot be found
        """
        # Direct instance ID
        if self.config.instance_id:
            # Verify instance exists
            if self._verify_instance_exists(self.config.instance_id):
                return self.config.instance_id
            else:
                raise InstanceNotFoundError(
                    f"Instance with ID '{self.config.instance_id}' not found",
                    instance_id=self.config.instance_id
                )
        
        # Find by name tag
        if self.config.instance_name:
            try:
                response = self.ec2_client.describe_instances(
                    Filters=[
                        {'Name': 'tag:Name', 'Values': [self.config.instance_name]},
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}
                    ]
                )
                
                instances = []
                for reservation in response['Reservations']:
                    instances.extend(reservation['Instances'])
                
                if not instances:
                    raise InstanceNotFoundError(
                        f"No instance found with name tag: {self.config.instance_name}",
                        instance_name=self.config.instance_name
                    )
                
                if len(instances) > 1:
                    self.logger.warning(
                        f"Multiple instances found with name: {self.config.instance_name}. "
                        "Using the first one found."
                    )
                
                return instances[0]['InstanceId']
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                raise AWSConnectionError(
                    f"Failed to find instance by name: {e}",
                    aws_error_code=error_code
                ) from e
        
        raise InstanceNotFoundError(
            "No instance_id or instance_name specified in configuration"
        )
    
    def _verify_instance_exists(self, instance_id: str) -> bool:
        """Verify that an instance exists."""
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            return bool(response['Reservations'])
        except ClientError:
            return False
    
    def get_instance_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed instance information.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            Dictionary with instance information or None if not found
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            
            if not response['Reservations']:
                self.logger.error(f"Instance {instance_id} not found")
                return None
            
            instance = response['Reservations'][0]['Instances'][0]
            
            return {
                'instance_id': instance['InstanceId'],
                'state': instance['State']['Name'],
                'public_ip': instance.get('PublicIpAddress'),
                'private_ip': instance.get('PrivateIpAddress'),
                'instance_type': instance['InstanceType'],
                'launch_time': instance.get('LaunchTime'),
                'availability_zone': instance['Placement']['AvailabilityZone'],
                'vpc_id': instance.get('VpcId'),
                'subnet_id': instance.get('SubnetId'),
                'security_groups': [sg['GroupName'] for sg in instance.get('SecurityGroups', [])],
                'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])},
                'platform': instance.get('Platform', 'linux'),
                'architecture': instance.get('Architecture', 'x86_64'),
                'monitoring': instance.get('Monitoring', {}).get('State', 'disabled'),
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            self.logger.error(f"Failed to get instance info: {e}")
            raise AWSConnectionError(
                f"Failed to get instance information: {e}",
                aws_error_code=error_code
            ) from e
    
    def get_instance_state(self, instance_id: str) -> Optional[str]:
        """Get the current state of the instance.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            Instance state string or None if not found
        """
        info = self.get_instance_info(instance_id)
        return info['state'] if info else None
    
    def get_public_ip(self, instance_id: str) -> Optional[str]:
        """Get the current public IP of the instance.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            Public IP address or None if not available
        """
        info = self.get_instance_info(instance_id)
        if info and info['state'] == 'running':
            return info['public_ip']
        return None
    
    def start_instance(self, instance_id: str) -> bool:
        """Start the EC2 instance if it's stopped.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            True if instance was started successfully, False otherwise
        """
        try:
            current_state = self.get_instance_state(instance_id)
            
            if current_state == 'running':
                self.logger.info(f"Instance {instance_id} is already running")
                return True
            
            if current_state not in ['stopped']:
                self.logger.warning(
                    f"Instance {instance_id} is in state '{current_state}', cannot start"
                )
                return False
            
            self.logger.info(f"Starting instance {instance_id}...")
            self.ec2_client.start_instances(InstanceIds=[instance_id])
            
            # Wait for instance to be running
            return self.wait_for_state(instance_id, 'running')
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                raise PermissionError(
                    "Insufficient permissions to start EC2 instance",
                    resource_type="ec2_instance",
                    resource_path=instance_id,
                    required_permissions=["ec2:StartInstances"]
                )
            
            self.logger.error(f"Failed to start instance: {e}")
            raise AWSConnectionError(
                f"Failed to start instance: {e}",
                aws_error_code=error_code
            ) from e
    
    def stop_instance(self, instance_id: str) -> bool:
        """Stop the EC2 instance.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            True if instance was stopped successfully, False otherwise
        """
        try:
            current_state = self.get_instance_state(instance_id)
            
            if current_state == 'stopped':
                self.logger.info(f"Instance {instance_id} is already stopped")
                return True
            
            if current_state not in ['running']:
                self.logger.warning(
                    f"Instance {instance_id} is in state '{current_state}', cannot stop"
                )
                return False
            
            self.logger.info(f"Stopping instance {instance_id}...")
            self.ec2_client.stop_instances(InstanceIds=[instance_id])
            
            # Wait for instance to be stopped
            return self.wait_for_state(instance_id, 'stopped')
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                raise PermissionError(
                    "Insufficient permissions to stop EC2 instance",
                    resource_type="ec2_instance",
                    resource_path=instance_id,
                    required_permissions=["ec2:StopInstances"]
                )
            
            self.logger.error(f"Failed to stop instance: {e}")
            raise AWSConnectionError(
                f"Failed to stop instance: {e}",
                aws_error_code=error_code
            ) from e
    
    def wait_for_state(self, instance_id: str, target_state: str, timeout: Optional[int] = None) -> bool:
        """Wait for instance to reach target state.
        
        Args:
            instance_id: EC2 instance ID
            target_state: Target state to wait for
            timeout: Maximum wait time in seconds
            
        Returns:
            True if target state reached, False if timeout
        """
        if timeout is None:
            timeout = self.config.max_wait_time
        
        self.logger.info(f"Waiting for instance {instance_id} to reach state '{target_state}'...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_state = self.get_instance_state(instance_id)
            
            if current_state == target_state:
                self.logger.info(f"Instance {instance_id} reached state '{target_state}'")
                return True
            
            if current_state in ['terminated', 'terminating']:
                self.logger.error(f"Instance {instance_id} is terminated")
                return False
            
            self.logger.debug(f"Instance state: {current_state}, waiting...")
            time.sleep(10)
        
        self.logger.error(
            f"Timeout waiting for instance {instance_id} to reach state '{target_state}'"
        )
        return False

    def ensure_instance_running(self, instance_id: str) -> Optional[str]:
        """Ensure instance is running and return its public IP.

        Args:
            instance_id: EC2 instance ID

        Returns:
            Public IP address if instance is running, None otherwise
        """
        current_state = self.get_instance_state(instance_id)

        if current_state == 'running':
            ip = self.get_public_ip(instance_id)
            if ip:
                self.logger.info(f"Instance {instance_id} is running at {ip}")
                return ip
            else:
                self.logger.warning(f"Instance {instance_id} is running but has no public IP")
                return None

        if current_state == 'stopped' and self.config.auto_start_instance:
            self.logger.info(f"Instance {instance_id} is stopped, attempting to start...")
            if self.start_instance(instance_id):
                # Wait a bit more for networking to be ready
                time.sleep(30)
                ip = self.get_public_ip(instance_id)
                if ip:
                    self.logger.info(f"Instance {instance_id} started successfully at {ip}")
                    return ip
                else:
                    self.logger.error(f"Instance {instance_id} started but has no public IP")
                    return None
            else:
                self.logger.error(f"Failed to start instance {instance_id}")
                return None

        self.logger.error(
            f"Instance {instance_id} is in state '{current_state}' and auto-start is disabled"
        )
        return None

    def get_instance_costs(self, instance_id: str) -> Dict[str, Any]:
        """Get basic cost information for the instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            Dictionary with cost information
        """
        info = self.get_instance_info(instance_id)
        if info:
            return {
                'instance_type': info['instance_type'],
                'state': info['state'],
                'launch_time': info.get('launch_time'),
                'estimated_hourly_cost': self._get_estimated_cost(info['instance_type']),
                'region': self.config.region,
                'availability_zone': info.get('availability_zone'),
            }
        return {}

    def _get_estimated_cost(self, instance_type: str) -> float:
        """Get estimated hourly cost for instance type.

        Note: These are simplified estimates. Actual costs vary by region,
        usage patterns, and AWS pricing changes.

        Args:
            instance_type: EC2 instance type

        Returns:
            Estimated hourly cost in USD
        """
        # Simplified cost estimates for common instance types
        cost_map = {
            # General Purpose
            't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208,
            't3.medium': 0.0416, 't3.large': 0.0832, 't3.xlarge': 0.1664,
            't2.nano': 0.0058, 't2.micro': 0.0116, 't2.small': 0.023,
            't2.medium': 0.046, 't2.large': 0.092, 't2.xlarge': 0.184,
            # Compute Optimized
            'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34,
            'c5.4xlarge': 0.68, 'c5.9xlarge': 1.53, 'c5.18xlarge': 3.06,
            # Memory Optimized
            'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504,
            'r5.4xlarge': 1.008, 'r5.8xlarge': 2.016, 'r5.16xlarge': 4.032,
            # General Purpose (M5)
            'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384,
            'm5.4xlarge': 0.768, 'm5.8xlarge': 1.536, 'm5.16xlarge': 3.072,
        }
        return cost_map.get(instance_type, 0.0)
