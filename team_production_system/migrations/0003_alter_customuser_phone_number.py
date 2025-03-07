# Generated by Django 4.1.7 on 2023-05-04 19:47

from django.db import migrations
import phonenumber_field.modelfields


class Migration(migrations.Migration):

    dependencies = [
        ('team_production_system', '0002_alter_mentee_team_number_alter_mentor_about_me_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='phone_number',
            field=phonenumber_field.modelfields.PhoneNumberField(blank=True, default='', max_length=128, null=True, region=None, unique=True),
        ),
    ]
