from .models import CustomUser, Mentee, Availability
from .models import Session, Mentor
from rest_framework import generics, status
from .serializers import CustomUserSerializer, AvailabilitySerializer
from .serializers import SessionSerializer
from .serializers import MentorListSerializer, MentorProfileSerializer
from .serializers import MenteeListSerializer, MenteeProfileSerializer
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .custom_permissions import IsMentorMentee
from datetime import datetime, timedelta
from rest_framework.parsers import MultiPartParser
from django.core.exceptions import ValidationError
from django.conf import settings
import boto3


# View to update the user profile information
class UserProfile(generics.RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get_object(self):
        user = self.request.user
        if not user.is_authenticated:
            return Response({'error': 'User is not authenticated.'},
                            status=status.HTTP_401_UNAUTHORIZED)

        try:
            return user
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': 'An unexpected error occured.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return user

    def patch(self, request, *args, **kwargs):
        user = self.request.user

        fields = ['first_name', 'last_name', 'email',
                  'phone_number', 'is_mentor', 'is_mentee', 'is_active']

        for field in fields:
            if field in request.data:
                setattr(user, field, request.data[field])

        if 'profile_photo' in request.FILES:
            if user.profile_photo:
                s3 = boto3.client('s3')
                s3.delete_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=user.profile_photo.name)

            user.profile_photo = request.FILES['profile_photo']

        user.save()
        serializer = CustomUserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


# View to see a list of all users flagged as a mentor
class MentorList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = CustomUser.objects.filter(is_mentor=True)
    serializer_class = MentorListSerializer

    def get(self, request, *args, **kwargs):
        queryset = CustomUser.objects.filter(is_mentor=True)

        if not queryset.exists():
            return Response({"message": "No mentors found."},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = MentorListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MentorFilteredList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        skills = self.kwargs['skills'].split(',')
        queryset = Mentor.objects.filter(skills__icontains=skills[0])
        for skill in skills[1:]:
            queryset = queryset.filter(skills__icontains=skill)

        if not queryset.exists():
            return Response({"message": "No mentors found."},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = MentorProfileSerializer(queryset, many=True)
        return Response(serializer.data)


# View to allow mentors to create and view the about me/skills.
class MentorInfoView(generics.ListCreateAPIView):
    serializer_class = MentorProfileSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        return Mentor.objects.filter(user=self.request.user)


# View to edit the logged in mentors about me and skills
class MentorInfoUpdateView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MentorProfileSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_object(self):
        return self.request.user.mentor


# View to see a list of all users flagged as a mentee
class MenteeList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            queryset = CustomUser.objects.filter(is_mentee=True)
        except Exception as e:
            return Response({"error": "Failed to retrieve mentee list."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not queryset:
            return Response({"message": "No mentees found."},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = MenteeListSerializer(queryset, many=True)
        response_data = serializer.data
        return Response(response_data)


# View to allow mentees to create and view the about me/skills.
class MenteeInfoView(generics.ListCreateAPIView):
    serializer_class = MenteeProfileSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        return Mentee.objects.filter(user=self.request.user)


# View to edit the logged in mentees team number
class MenteeInfoUpdateView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MenteeProfileSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_object(self):
        return self.request.user.mentee


# Create and view all availabilities
class AvailabilityView(generics.ListCreateAPIView):
    serializer_class = AvailabilitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Exclude any availability that has an end time in the past
        return Availability.objects.filter(end_time__gte=timezone.now())

    def get(self, request):
        try:
            availabilities = self.get_queryset()

            # Check if there are any availabilities
            if not availabilities:
                return Response("No open availabilities.",
                                status=status.HTTP_404_NOT_FOUND)

            serializer = self.serializer_class(availabilities, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except:
            return Response("Error: Failed to retrieve availabilities.",
                            status=status.HTTP_400_BAD_REQUEST)


# Time conversion helper function
# During a session request, must convert start_time string to a datetime
# object in order to use timedelta to check for overlapping sessions
def time_convert(time, minutes):
    # Convert string from front end to datetime object
    datetime_obj = datetime.strptime(time, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    # Change time dependent on session length minutes
    datetime_delta = datetime_obj - timedelta(minutes=minutes)
    # Convert datetime object back to string
    new_start_time = datetime.strftime(
        datetime_delta, '%Y-%m-%d %H:%M:%S%z')[:-2]
    return new_start_time


# Create and view all sessions
class SessionRequestView(generics.ListCreateAPIView):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Get the mentor availability ID from the request data
        mentor_availability_id = self.request.data.get('mentor_availability')

        # Get the mentor availability instance
        mentor_availability = Availability.objects.get(
            id=mentor_availability_id)

        # Ensure no overlap between mentor or mentee's sessions
        mentor = mentor_availability.mentor

        mentee = Mentee.objects.get(user=self.request.user)

        start_time = self.request.data['start_time']
        session_length = self.request.data['session_length']

        if session_length == 30:
            new_start_time = time_convert(start_time, session_length)

            if Session.objects.filter(
                Q(mentor=mentor, start_time=start_time,
                  status__in=['Pending', 'Confirmed']) |
                Q(mentor=mentor, start_time=new_start_time,
                  session_length=60, status__in=['Pending', 'Confirmed'])
            ).exists():
                raise ValidationError(
                    'A session with this mentor is already scheduled during this time.')

            elif Session.objects.filter(
                Q(mentee=mentee, start_time=start_time, status__in=['Pending', 'Confirmed']) |
                Q(mentee=mentee, start_time=new_start_time,
                  session_length=60, status__in=['Pending', 'Confirmed'])
            ).exists():
                raise ValidationError(
                    'A session with this mentee is already scheduled during this time.')

            # Set the mentor for the session
            else:
                serializer.save(mentor=mentor,
                                mentor_availability=mentor_availability,
                                mentee=mentee)

            # Email notification to the mentor
                session = serializer.instance
                session.mentor_session_notify()

        if session_length == 60:
            before_start_time = time_convert(start_time, 30)
            after_start_time = time_convert(start_time, -30)

            if Session.objects.filter(
                Q(mentor=mentor, start_time=start_time, status__in=['Pending', 'Confirmed']) |
                Q(mentor=mentor, start_time=before_start_time, session_length=60, status__in=['Pending', 'Confirmed']) |
                Q(mentor=mentor, start_time=after_start_time,
                  status__in=['Pending', 'Confirmed'])
            ).exists():
                raise ValidationError(
                    'A session with this mentor is already scheduled during this time.')

            elif Session.objects.filter(
                Q(mentee=mentee, start_time=start_time,
                  status__in=['Pending', 'Confirmed']) |
                Q(mentee=mentee, start_time=before_start_time,
                  session_length=60, status__in=['Pending', 'Confirmed']) |
                Q(mentee=mentee, start_time=after_start_time,
                  status__in=['Pending', 'Confirmed'])
            ).exists():
                raise ValidationError(
                    'A session with this mentee is already scheduled during this time.')

            # Set the mentor for the session
            else:
                serializer.save(mentor=mentor,
                                mentor_availability=mentor_availability,
                                mentee=mentee)

            # Email notification to the mentor
                session = serializer.instance
                session.mentor_session_notify()


class SessionRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [IsMentorMentee]

    # Update the session status
    def perform_update(self, serializer):
        # Email notification if the session is cancelled
        session = serializer.instance
        status = self.request.data.get('status')

        if status == 'Canceled':
            session.status = status
            session.save()
            session.session_cancel_notify()
        else:
            serializer.save()


class SessionView(generics.ListAPIView):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Get sessions for the logged in user
        return Session.objects.filter(Q(mentor__user=self.request.user) |
                                      Q(mentee__user=self.request.user),
                                      start_time__gte=timezone.now() - timedelta(hours=24))


class ArchiveSessionView(generics.ListAPIView):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Get sessions for the logged in user
        return Session.objects.filter(Q(mentor__user=self.request.user) |
                                      Q(mentee__user=self.request.user),
                                      start_time__lt=timezone.now() - timedelta(hours=24))
